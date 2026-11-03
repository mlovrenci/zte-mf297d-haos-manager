"""ZTE Manager v0.4.5: HAOS Ingress, local UI and explicitly approved ZTE Goform writes."""
import ipaddress
import json
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock
from time import monotonic, time
from zte_api import RouterClient, RouterError

VERSION = "0.4.5"
HERE = Path(__file__).resolve().parent
OPTIONS = Path(os.environ.get("ZTE_OPTIONS_PATH", "/data/options.json"))
AUDIT = Path(os.environ.get("ZTE_AUDIT_PATH", "/data/zte_audit.jsonl"))
HISTORY = Path(os.environ.get("ZTE_HISTORY_PATH", "/data/zte_history.sqlite3"))
CSRF = secrets.token_urlsafe(32)
STORE_LOCK = RLock()
ROUTER_LOCK = RLock()
PEERS = {"172.30.32.2", "127.0.0.1", "::1"}
LOCK = RLock()
PLANS = {}


def options():
    try:
        obj = json.loads(OPTIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        obj = {}
    ip = str(obj.get("router_ip", "192.168.1.1"))
    addr = ipaddress.ip_address(ip)
    if not isinstance(addr, ipaddress.IPv4Address) or not addr.is_private or addr.is_loopback or addr.is_link_local:
        raise ValueError("Nevaljana privatna LAN IP adresa routera")
    return {"ip": ip, "password": str(obj.get("router_password") or ""),
            "timeout": min(20, max(2, int(obj.get("timeout_seconds", 6)))),
            "firmware": str(obj.get("expected_firmware") or ""),
            "write_enabled": obj.get("write_enabled") is True,
            "disruptive": obj.get("allow_disruptive_changes") is True,
            "apn": obj.get("allow_apn_changes") is True,
            "history": obj.get("monitor_enabled") is True,
            "interval": min(3600, max(120, int(obj.get("monitor_interval_seconds", 300)))),
            "verified_writes": obj.get("b08_write_verified") is True,
            "experimental_writes": obj.get("allow_experimental_writes") is True,
            "wifi_format": str(obj.get("wifi_password_format", "unknown")),
            "allow_reboot": obj.get("allow_system_reboot") is True}


def connect(o):
    if not o["password"]:
        raise RouterError("Postavi router_password u konfiguraciji HAOS aplikacije")
    client = RouterClient(o["ip"], o["timeout"])
    client.login(o["password"])
    return client


def validate_ipv4(value):
    try:
        ip = ipaddress.IPv4Address(str(value))
    except ipaddress.AddressValueError as exc:
        raise ValueError("Nevaljana IPv4 adresa") from exc
    return str(ip)


def plan_operation(op, data, groups, o):
    """Pure planning; no ZTE mutation. Checked again on commit."""
    if not o.get("write_enabled") or not o.get("experimental_writes"):
        raise ValueError("Write zaključan: uključi write_enabled i allow_experimental_writes u HAOS postavkama")
    fw = groups.get("device", {}).get("cr_version", "")
    if not fw or not o["firmware"] or fw.strip() != o["firmware"].strip():
        raise ValueError("Firmware nije jednak očekivanoj verziji. Write nije dopušten")
    lan = groups.get("lan", {})
    dhcp = groups.get("dhcp", {})
    wifi = groups.get("wifi", {})
    wan = groups.get("internet", {})
    if op == "dhcp":
        if not lan.get("lan_ipaddr") or not lan.get("lan_netmask") or "dhcpEnabled" not in dhcp:
            raise ValueError("B08 nije vratio potpune LAN/DHCP parametre")
        gateway, netmask = lan["lan_ipaddr"], lan["lan_netmask"]
        net = ipaddress.IPv4Network(f"{gateway}/{netmask}", strict=False)
        enabled = data.get("enabled") is True
        if not enabled and not o["disruptive"]:
            raise ValueError("Za DHCP OFF uključi allow_disruptive_changes u HAOS Apps opcijama")
        if not enabled and data.get("recovery_ready") is not True:
            raise ValueError("Za DHCP OFF potvrdi fizički pristup routeru, statički IP računala i aktivan drugi DHCP server")
        start = validate_ipv4(data.get("start"))
        end = validate_ipv4(data.get("end"))
        if ipaddress.IPv4Address(start) not in net or ipaddress.IPv4Address(end) not in net:
            raise ValueError("DHCP pool mora biti u postojećem LAN subnetu")
        if not (net.network_address < ipaddress.IPv4Address(start) <= ipaddress.IPv4Address(end) < net.broadcast_address):
            raise ValueError("Neispravan DHCP pool")
        if ipaddress.IPv4Address(start) <= ipaddress.IPv4Address(gateway) <= ipaddress.IPv4Address(end):
            raise ValueError("Gateway ne smije biti unutar DHCP poola")
        lease = int(data.get("lease_hours"))
        if not 1 <= lease <= 168:
            raise ValueError("Lease mora biti 1–168 sati")
        if not enabled and str(dhcp.get("dhcpEnabled")) not in ("1", "true", "True"):
            raise ValueError("DHCP na routeru nije potvrđeno uključen")
        params = {"lanIp": gateway, "lanNetmask": netmask,
                  "lanDhcpType": "SERVER" if enabled else "DISABLE",
                  "dhcpStart": start, "dhcpEnd": end, "dhcpLease": str(lease*3600),
                  "dhcp_reboot_flag": "1", "mac_ip_reset": "0"}
        summary = f"DHCP {'ON' if enabled else 'OFF'} · {start}–{end} · {lease} h. Router se može restartati."
        return "DHCP_SETTING", params, summary, ("DHCP_ISKLJUCI" if not enabled else "POTVRDI"), ["lan", "dhcp"]
    if op == "dns":
        dns = groups.get("dns", {})
        if "dns_mode" not in dns:
            raise ValueError("Nema očitanog dns_mode; DNS write je blokiran")
        mode = data.get("mode")
        if mode not in ("auto", "manual"):
            raise ValueError("DNS način mora biti auto ili manual")
        if mode == "manual":
            primary = validate_ipv4(data.get("primary"))
            secondary = validate_ipv4(data.get("secondary"))
            if primary == "0.0.0.0" or secondary == "0.0.0.0":
                raise ValueError("DNS server ne smije biti 0.0.0.0")
            params = {"dns_mode": "manual", "prefer_dns_manual":primary, "standby_dns_manual":secondary}
            summary = f"WAN DNS: manual, {primary} / {secondary}. Ne mijenja nužno DHCP DNS opciju 6."
        else:
            params = {"dns_mode":"auto", "prefer_dns_manual":"", "standby_dns_manual":""}
            summary = "WAN DNS: automatski (operater). Ne mijenja nužno DHCP DNS opciju 6."
        return "ROUTER_DNS_SETTING", params, summary, "DNS_PROMJENA", ["dns"]
    if op == "wifi_power":
        if not o.get("disruptive"):
            raise ValueError("Wi-Fi ON/OFF zahtijeva allow_disruptive_changes")
        if "wifi_onoff_state" not in wifi:
            raise ValueError("Wi-Fi glavni status nije vraćen na firmwareu B08")
        enabled = data.get("enabled") is True
        if not enabled and data.get("recovery_ready") is not True:
            raise ValueError("Wi-Fi OFF zahtijeva potvrdu žičnog pristupa za oporavak")
        return "SET_WIFI_INFO", {"wifiEnabled": "1" if enabled else "0", "m_ssid_enable":"0"}, \
            f"Wi-Fi {'ON' if enabled else 'OFF'} — prekida Wi-Fi klijente, uključujući Honor, kamere i telefone.", \
            "WIFI_ISKLJUCI" if not enabled else "WIFI_UKLJUCI", ["wifi"]
    if op == "wan_link":
        if not o.get("disruptive"):
            raise ValueError("WAN connect/disconnect zahtijeva allow_disruptive_changes")
        if "ppp_status" not in wan:
            raise ValueError("WAN status nije dostupan")
        enabled = data.get("connected") is True
        if not enabled and data.get("recovery_ready") is not True:
            raise ValueError("WAN disconnect zahtijeva potvrdu fizičkog pristupa za oporavak")
        return ("CONNECT_NETWORK" if enabled else "DISCONNECT_NETWORK"), {}, \
            ("Spoji 4G WAN" if enabled else "Odspoji 4G WAN i prekini kućni internet"), \
            ("WAN_SPOJI" if enabled else "WAN_ODSPJI"), ["internet"]
    if op == "wifi_primary":
        if not o["disruptive"]:
            raise ValueError("Wi-Fi promjene traže allow_disruptive_changes")
        if not wifi.get("wifi_chip1_ssid1_ssid") or not wifi.get("wifi_chip1_ssid1_auth_mode"):
            raise ValueError("Nedostaju potvrđene informacije o glavnom Wi-Fi SSID-u")
        ssid = str(data.get("ssid", ""))
        pwd = str(data.get("wifi_password", ""))
        if not 1 <= len(ssid.encode("utf-8")) <= 32 or any(ord(c)<32 for c in ssid):
            raise ValueError("SSID mora imati 1–32 bajta")
        if not 8 <= len(pwd) <= 63 or any(ord(c)<32 for c in pwd):
            raise ValueError("WPA2 zaporka mora imati 8–63 znaka")
        # MF297D B08 does not disclose PASSWORD_ENCODE. Require an explicit
        # user-selected protocol format (never infer from password-like fields).
        mode = o.get("wifi_format", "unknown")
        if mode not in ("plain", "base64"):
            raise ValueError("U App postavkama prvo odaberi wifi_password_format (plain ili base64) nakon provjere firmwarea")
        if mode == "base64":
            import base64
            pwd = base64.b64encode(pwd.encode("utf-8")).decode("ascii")
        params = {"ssid": ssid, "broadcastSsidEnabled": "1", "MAX_Access_num": str(wifi.get("wifi_chip1_ssid1_max_access_num", "32")),
                  "security_mode": "WPA2PSK", "cipher": "1", "NoForwarding": "0",
                  "qrcode_display_switch": "0", "security_shared_mode": "AES", "passphrase": pwd}
        return "SET_WIFI_SSID1_SETTINGS", params, f"Promjena primarnog Wi-Fi SSID-a u {ssid}; mogući prekid Wi-Fi-ja.", "WIFI_PROMJENA", ["wifi"]
    if op == "bearer":
        if not o["disruptive"]:
            raise ValueError("4G mode promjene traže allow_disruptive_changes")
        mode = data.get("mode")
        if mode not in ("Only_LTE", "NETWORK_auto"):
            raise ValueError("Dopušteni su samo Only_LTE i NETWORK_auto")
        if not wan.get("BearerPreference"):
            raise ValueError("Router ne vraća BearerPreference; način rada nije verificiran")
        return "SET_BEARER_PREFERENCE", {"BearerPreference": mode}, f"Mrežni način: {'samo 4G' if mode == 'Only_LTE' else 'automatski'}. Veza se može prekinuti.", "4G_PROMJENA", ["internet"]
    if op == "apn":
        if not o["apn"] or not o["disruptive"]:
            raise ValueError("APN write zahtijeva allow_apn_changes i allow_disruptive_changes")
        if not wan.get("apn_interface_version") or not wan.get("wan_apn"):
            raise ValueError("APN format B08 nije utvrđen. Promjena je blokirana")
        # This branch is intentionally disabled until a B08 API capture is available;
        # otherwise an incorrect profile index can wipe the working HT connection.
        raise ValueError("APN write još čeka potvrdu B08 profila i indeksa; prikaz je read-only")
    if op == "wan_connection":
        if not o["disruptive"]: raise ValueError("4G promjene traže allow_disruptive_changes")
        mode = data.get("mode")
        if mode not in ("auto_dial", "manual_dial"):
            raise ValueError("Nepodržan 4G način povezivanja")
        if not wan.get("ppp_status"):
            raise ValueError("WAN status nije dostupan")
        return "SET_CONNECTION_MODE", {"ConnectionMode":mode, "roam_setting_option":"off"}, \
            "Promjena WAN dial načina može prekinuti internet; A1 B08 write još nije dokazan.", "4G_PROMJENA", ["internet"]
    if op == "upnp":
        if not o["disruptive"]: raise ValueError("UPnP write zahtijeva allow_disruptive_changes")
        net = groups.get("network_extra", {})
        if not any(k in net for k in ("upnp_enable", "upnp_setting_option", "upnp_status")):
            raise ValueError("UPnP API nije vraćen na B08; write nije dopušten")
        enabled = data.get("enabled") is True
        return "UPNP_SETTING", {"upnp_setting_option":"1" if enabled else "0"}, \
            "UPnP: "+("ON" if enabled else "OFF")+"; moguć utjecaj na aplikacije i portove.", "UPNP_PROMJENA", ["network_extra"]
    if op == "dmz":
        if not o["disruptive"]: raise ValueError("DMZ write zahtijeva allow_disruptive_changes")
        net = groups.get("network_extra", {})
        if not any(k in net for k in ("DMZEnable", "DMZIPAddress")):
            raise ValueError("DMZ polja nisu vraćena na B08; write nije dopušten")
        enabled = data.get("enabled") is True
        params = {"DMZEnabled": "1" if enabled else "0"}
        if enabled:
            target = validate_ipv4(data.get("address"))
            network = ipaddress.IPv4Network(f"{lan['lan_ipaddr']}/{lan['lan_netmask']}", strict=False)
            if ipaddress.IPv4Address(target) not in network or target == lan["lan_ipaddr"]:
                raise ValueError("DMZ IP mora biti LAN klijent, ne gateway")
            params["DMZIPAddress"] = target
        return "DMZ_SETTING", params, "DMZ mijenja izloženost LAN uređaja internetu; nikad ne izlagati HAOS.", "DMZ_PROMJENA", ["network_extra", "lan"]
    if op == "reboot":
        if not o["disruptive"] or not o.get("allow_reboot"):
            raise ValueError("Restart zahtijeva allow_disruptive_changes i allow_system_reboot")
        return "REBOOT_DEVICE", {}, "Potpuni restart ZTE-a. Internet, Wi-Fi i Tailscale bit će privremeno nedostupni.", "RESTART_ZTE", ["device"]
    raise ValueError("Nedopuštena operacija")


def snapshot(groups, names):
    return json.dumps({name: groups.get(name, {}) for name in names}, sort_keys=True, ensure_ascii=True)


def safe_log(op, status):
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": int(time()), "operation": op, "status": status}) + "\n")
        os.chmod(AUDIT, 0o600)
    except OSError:
        pass



# Local, password-free history. No serial number, MAC, IMEI, SIM identifier or password persisted.
def init_history():
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with STORE_LOCK, sqlite3.connect(HISTORY) as db:
        db.execute("CREATE TABLE IF NOT EXISTS samples (ts INTEGER PRIMARY KEY, rsrp REAL, rsrq REAL, sinr REAL, down REAL, up REAL, wan TEXT, operator TEXT, cell TEXT)")
        db.execute("CREATE INDEX IF NOT EXISTS ix_samples_ts ON samples(ts)")

def _float(v):
    try:
        # Some versions return ' -95 dBm', the API values in practice mostly numeric.
        import re
        m = re.search(r"-?\d+(?:\.\d+)?", str(v))
        return float(m.group()) if m else None
    except (ValueError, TypeError):
        return None

def record_sample(groups):
    try:
        sg=groups.get("signal", {}); tg=groups.get("traffic", {}); ng=groups.get("internet", {})
        now=int(time())
        init_history()
        with STORE_LOCK, sqlite3.connect(HISTORY) as db:
            last=db.execute("SELECT MAX(ts) FROM samples").fetchone()[0]
            if last is not None and now-last < 120: return
            db.execute("INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?,?)",
              (now, _float(sg.get("lte_rsrp")), _float(sg.get("lte_rsrq")),
               _float(sg.get("lte_snr", sg.get("Z_SINR"))),
               _float(tg.get("realtime_rx_thrpt", tg.get("realtime_rx_thrp"))), _float(tg.get("realtime_tx_thrpt", tg.get("realtime_tx_thrp"))),
               str(ng.get("ppp_status", ""))[:48], str(ng.get("network_provider", ""))[:64],
               str(sg.get("cell_id", ""))[:64]))
            db.execute("DELETE FROM samples WHERE ts < ?", (now-14*86400,))
    except (OSError, sqlite3.Error):
        pass

def read_history(hours):
    init_history()
    with STORE_LOCK, sqlite3.connect(HISTORY) as db:
        rows=db.execute("SELECT ts,rsrp,rsrq,sinr,down,up,wan,operator,cell FROM samples WHERE ts>=? ORDER BY ts LIMIT 5000", (int(time())-hours*3600,)).fetchall()
    return [dict(zip(("ts","rsrp","rsrq","sinr","down","up","wan","operator","cell"),row)) for row in rows]

def capabilities(groups):
    """Classify *read* availability from fields B08 actually returned.

    A partial category still has useful data. Never infer write support here.
    """
    specs = {
      "status": ("device", ["cr_version"], ["wa_inner_version", "hardware_version"]),
      "4g": ("internet", ["network_type", "ppp_status"], ["wan_apn", "network_provider"]),
      "signal": ("signal", ["lte_rsrp"], ["Z_SINR", "lte_rsrq", "wan_lte_ca"]),
      "lan": ("lan", ["lan_ipaddr", "lan_netmask"], []),
      "dhcp": ("dhcp", ["dhcpEnabled", "dhcpStart", "dhcpEnd"], ["dhcpLease_hour", "dhcpLease"]),
      "dns": ("dns", ["dns_mode"], ["prefer_dns_manual", "standby_dns_manual", "dns_primary_dns", "dns_secondary_dns"]),
      "wifi": ("wifi", ["wifi_chip1_ssid1_ssid", "wifi_chip2_ssid1_ssid"], ["wifi_chip1_ssid1_auth_mode", "wifi_chip2_ssid1_auth_mode"]),
      "wifi_extra": ("wifi_extra", ["wifi_chip1_ssid1_switch_onoff", "wifi_chip2_ssid1_switch_onoff"], ["wifi_chip1_ssid2_switch_onoff", "wifi_chip2_ssid2_switch_onoff"]),
      "traffic": ("traffic", ["realtime_rx_thrpt", "realtime_tx_thrpt", "realtime_rx_thrp", "realtime_tx_thrp"], ["realtime_rx_bytes", "realtime_tx_bytes", "monthly_rx_bytes", "monthly_tx_bytes", "total_rx_bytes", "total_tx_bytes"]),
      "nat": ("network_extra", ["upnp_enable", "dmz_switch"], ["nat_type", "ipv6_enable", "rj45_state"]),
      "system": ("system_extra", ["uptime", "sys_uptime", "system_uptime", "router_uptime"], ["sntp_time_set_mode", "sntp_timezone"]),
    }
    result = {}
    for name, (grp, primary, auxiliary) in specs.items():
        data = groups.get(grp, {})
        prim = [k for k in primary if data.get(k) not in (None, "")]
        extra = [k for k in auxiliary if data.get(k) not in (None, "") and k not in prim]
        # Existence of any useful value is evidence of read support, even
        # when a throughput/uptime metric specifically is missing.
        fields = prim + extra
        result[name] = {
            "status": "available" if prim else ("partial" if extra else "not_returned"),
            "fields": fields,
            "detail": (
                "Brzine i brojači" if name == "traffic" and prim else
                "Brojači dostupni, brzina nije potvrđena" if name == "traffic" and extra else
                "Vrijeme dostupno, uptime nije potvrđen" if name == "system" and extra and not prim else
                "Samo DNS način rada, adrese nisu potvrđene" if name == "dns" and not extra and prim else
                "Dio podataka dostupan" if extra and not prim else ""
            ),
            "firmware_verified": False,  # WRITE not verified even if fw string matches
        }
    return result


def sanitized_network_snapshot(groups):
    """Small, deliberately allowlisted diagnostic values; no WAN IP, SIM, Wi-Fi, MAC or tokens."""
    allow = {
        "lan": ("lan_ipaddr", "lan_netmask"),
        "dhcp": ("dhcpEnabled", "dhcpStart", "dhcpEnd", "dhcpLease_hour", "dhcpLease"),
        "dns": ("dns_mode", "prefer_dns_manual", "standby_dns_manual", "dns_primary_dns", "dns_secondary_dns"),
    }
    return {group: {k: str(groups.get(group, {})[k])[:64]
                    for k in fields if groups.get(group, {}).get(k) not in (None, "")}
            for group, fields in allow.items()}

def monitor_loop():
    # Disabled by default. One small poll every N seconds when enabled.
    while True:
        try:
            o=options()
            if o["history"]:
                with ROUTER_LOCK:
                    client=connect(o)
                    groups, _=client.query_groups(["internet","signal","traffic"])
                record_sample(groups)
            threading.Event().wait(o["interval"])
        except (OSError, ValueError, RouterError):
            threading.Event().wait(300)


class Handler(BaseHTTPRequestHandler):
    server_version = "ZTEManager/0.4.5"

    def log_message(self, *args):
        pass  # passwords, tokens, URL params and POST bodies are not logged

    def response(self, code, obj, mime="application/json; charset=utf-8"):
        if isinstance(obj, (dict, list)):
            body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        elif isinstance(obj, str):
            body = obj.encode()
        else:
            body = obj
        self.send_response(code)
        for k,v in {"Content-Type": mime, "Content-Length": str(len(body)), "Cache-Control":"no-store",
                    "X-Content-Type-Options":"nosniff", "Referrer-Policy":"no-referrer",
                    "X-Frame-Options":"SAMEORIGIN",
                    "Content-Security-Policy":"default-src 'none'; img-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'self'"}.items():
            self.send_header(k,v)
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if self.client_address[0] not in PEERS:
            self.response(403, {"error": "Samo HAOS Ingress pristup"})
            return False
        return True

    def do_GET(self):
        if not self.allowed(): return
        path = self.path.split("?",1)[0]
        static = {"/": ("static/index.html", "text/html; charset=utf-8"),
                  "/index.html": ("static/index.html", "text/html; charset=utf-8"),
                  "/static/app.js": ("static/app.js", "application/javascript; charset=utf-8"),
                  "/static/style.css": ("static/style.css", "text/css; charset=utf-8")}
        if path in static:
            file, mime = static[path]
            return self.response(200, (HERE/file).read_bytes(),mime)
        try:
            o = options()
            if path == "/api/meta":
                return self.response(200, {"version":VERSION,"router_ip":o["ip"],"configured":bool(o["password"]),
                                           "write_enabled":o["write_enabled"],"verified_writes":o["verified_writes"],"experimental_writes":o["experimental_writes"],"disruptive":o["disruptive"],"apn":o["apn"],"wifi_format":o["wifi_format"],"allow_reboot":o["allow_reboot"],"monitor_enabled":o["history"],"monitor_interval_seconds":o["interval"],"csrf":CSRF,
                                           "expected_firmware":o["firmware"]})
            if path == "/api/state":
                with ROUTER_LOCK:
                    client = connect(o)
                    groups, errors = client.query_groups()
                if o["history"]: record_sample(groups)
                return self.response(200, {"groups":groups,"errors":errors,"authenticated":client.authenticated,
                                           "capabilities":capabilities(groups),"sample_time":int(time())})
            if path == "/api/clients":
                with ROUTER_LOCK:
                    client = connect(o)
                    clients, details = client.clients()
                    wired = client.lan_clients()
                return self.response(200, {"clients":clients,"wired":wired,"details":details})
            if path == "/api/dhcp_details":
                with ROUTER_LOCK:
                    client = connect(o)
                    details = client.dhcp_inventory()
                return self.response(200, details)
            if path == "/api/audit":
                rows = []
                if AUDIT.is_file():
                    rows = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines()[-30:] if line]
                return self.response(200, {"events":rows})
            if path == "/api/history":
                import urllib.parse
                query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                hrs=168 if query.get("hours",["24"])[0]=="168" else 24
                return self.response(200, {"enabled":o["history"],"hours":hrs,"samples":read_history(hrs)})
            if path == "/api/diagnostics":
                with ROUTER_LOCK:
                    c = connect(o); groups, errors = c.query_groups()
                return self.response(200, {"version":VERSION,
                    "reported_firmware":groups["device"].get("cr_version","not returned"),
                    "expected_firmware":o["firmware"],"match":groups["device"].get("cr_version")==o["firmware"],
                    "fields_present":{k:list(v) for k,v in groups.items()},"errors":errors,
                    "network_snapshot":sanitized_network_snapshot(groups),
                    "capabilities":capabilities(groups),"monitor_enabled":o["history"],
                    "dhcp_reservations":"not_verified_on_B08",
                    "dhcp_option_6_dns":"not_verified_on_B08",
                    "write_enabled":o["write_enabled"],"verified_writes":o["verified_writes"],"experimental_writes":o["experimental_writes"],
                    "apn_write_ready":False})
            return self.response(404, {"error":"Not found"})
        except (RouterError, ValueError, OSError) as e:
            return self.response(502, {"error":str(e)})

    def do_POST(self):
        if not self.allowed(): return
        if self.headers.get("X-ZTE-CSRF") != CSRF:
            return self.response(403, {"error":"CSRF token nije valjan; osvježi aplikaciju"})
        if self.headers.get("X-ZTE-Action") != "yes":
            return self.response(403, {"error":"Nedostaje zaštitno zaglavlje"})
        if self.headers.get("Content-Type", "").split(";",1)[0] != "application/json":
            return self.response(415, {"error":"Samo application/json"})
        # HA Ingress may rewrite Host; enforce a non-simple custom header and
        # deny browsers explicitly marking a cross-site fetch.
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return self.response(403, {"error":"Cross-site zahtjev odbijen"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 2048:
                return self.response(413, {"error":"Neispravna duljina zahtjeva"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError("Neispravan payload")
            o = options()
            if self.path == "/api/prepare":
                with ROUTER_LOCK:
                    client = connect(o)
                    groups, errors = client.query_groups()
                op = str(data.get("operation", ""))
                vals = data.get("values", {})
                if not isinstance(vals, dict): raise ValueError("Nevaljan obrazac")
                command, params, summary, confirm, watched = plan_operation(op, vals, groups, o)
                key = secrets.token_urlsafe(24)
                with LOCK:
                    for k in list(PLANS):
                        if PLANS[k]["exp"] < monotonic(): PLANS.pop(k)
                    PLANS.clear() # only one pending config-changing action at a time
                    PLANS[key] = {"exp":monotonic()+90,"op":op,"cmd":command,"params":params,
                                  "confirm":confirm,"watched":watched,"before":snapshot(groups,watched),
                                  "firmware":groups["device"].get("cr_version")}
                return self.response(200, {"plan_id":key,"summary":summary,"confirm":confirm,
                                           "expires_seconds":90,"warning":"Konfiguracijski write može privremeno prekinuti mrežu"})
            if self.path == "/api/apply":
                key = str(data.get("plan_id", ""))
                confirmation = str(data.get("confirmation", ""))
                with LOCK:
                    plan = PLANS.pop(key, None)
                if plan is None or plan["exp"] < monotonic():
                    raise ValueError("Pripremljena promjena je istekla; ponovi pripremu")
                if confirmation != plan["confirm"]:
                    raise ValueError("Potvrdni tekst nije točan; promjena nije izvršena")
                if not o["write_enabled"] or not o["experimental_writes"]: raise ValueError("Write nije otključan za eksperimentalne B08 naredbe")
                if plan["op"] in ("wifi_primary","wifi_power","wan_link","bearer","wan_connection","upnp","dmz","reboot") and not o["disruptive"]:
                    raise ValueError("Disruptive writes su isključeni")
                if plan["op"] == "reboot" and not o["allow_reboot"]:
                    raise ValueError("Restart nije dopušten")
                if plan["op"] == "dhcp" and plan["params"]["lanDhcpType"]=="DISABLE" and not o["disruptive"]:
                    raise ValueError("DHCP OFF blokiran")
                with ROUTER_LOCK:
                    client = connect(o)
                    new_groups, _ = client.query_groups()
                if new_groups["device"].get("cr_version") != plan["firmware"] or new_groups["device"].get("cr_version") != o["firmware"]:
                    raise ValueError("Firmware se promijenio; write odbijen")
                if snapshot(new_groups, plan["watched"]) != plan["before"]:
                    raise ValueError("Postavke su se promijenile između provjera; osvježi i ponovi")
                try:
                    with ROUTER_LOCK:
                        outcome = client.set(plan["cmd"], plan["params"])
                    safe_log(plan["op"], "router_accepted_unverified")
                except RouterError:
                    safe_log(plan["op"], "rejected_or_connection_lost")
                    raise
                # Some writes trigger immediate restart. Never treat a timeout as proof
                # of failure nor retry a mutation automatically.
                observed = None
                if plan["op"] in ("upnp", "dmz", "bearer", "wan_connection", "dns", "wifi_power", "wan_link", "dhcp"):
                    try:
                        with ROUTER_LOCK:
                            verify = connect(o)
                            new, _ = verify.query_groups(plan["watched"])
                        observed = {name: new.get(name, {}) for name in plan["watched"]}
                    except RouterError:
                        pass
                return self.response(200, {"status":"sent","router_response":outcome,
                    "after":observed,"note":"API je prihvatio zahtjev, ali postavke možda nisu spremljene. Provjeri stvarni rezultat nakon ponovnog očitanja. Ne šalji drugi put dok ne utvrdiš stanje."})
            return self.response(404, {"error":"Nepoznata operacija"})
        except (RouterError, ValueError, TypeError, KeyError) as e:
            return self.response(422, {"error":str(e)})


if __name__ == "__main__":
    print(f"ZTE Manager {VERSION}: HA Ingress @8099 (password not logged)", flush=True)
    threading.Thread(target=monitor_loop, name="zte-monitor", daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()