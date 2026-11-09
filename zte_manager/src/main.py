"""ZTE Manager v0.8.1: HAOS Ingress, local UI and explicitly approved ZTE Goform writes."""
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
from wifi_contracts import catalogue as wifi_contract_catalogue
from webui_evidence import (inspect as inspect_webui, inspect_wifi_modules,
                            inspect_wifi_channels, wifi_source, wifi_getter_source, wifi_ui_source,
                            wifi_feature_source, WIFI_FEATURE_NAMES)
from preview_data import collect as collect_preview, reservations as preview_reservations
from mqtt_probe import publish_probe, publish_dns_probe, MQTTProbeError
from dns_option6_probe import probe_dns_option6
from migration_inventory import capture_inventory, publish_inventory
from static_binding_test import listen_once as listen_static_binding_test
from static_reservations import validated_rows, prepare as prepare_reservation, execute as execute_reservation, reject_active_ip_collision

VERSION = "0.8.1"
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
STATIC_PLANS = {}
# UI override lasts until the app restarts; Supervisor options stay untouched.
WRITE_OVERRIDE = None


def options():
    try:
        obj = json.loads(OPTIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        obj = {}
    with LOCK:
        override = WRITE_OVERRIDE
    ip = str(obj.get("router_ip", "192.168.1.1"))
    addr = ipaddress.ip_address(ip)
    if not isinstance(addr, ipaddress.IPv4Address) or not addr.is_private or addr.is_loopback or addr.is_link_local:
        raise ValueError("Nevaljana privatna LAN IP adresa routera")
    return {"ip": ip, "password": str(obj.get("router_password") or ""),
            "timeout": min(20, max(2, int(obj.get("timeout_seconds", 6)))),
            "firmware": str(obj.get("expected_firmware") or ""),
            "write_enabled": (obj.get("write_enabled") is True) if override is None else override,
            "disruptive": obj.get("allow_disruptive_changes") is True,
            "apn": obj.get("allow_apn_changes") is True,
            "history": obj.get("monitor_enabled") is True,
            "mqtt_diagnostics": obj.get("mqtt_diagnostics_enabled") is True,
            "mqtt_startup_probe": obj.get("startup_probe_once", True) is True,
            "interval": min(3600, max(120, int(obj.get("monitor_interval_seconds", 300)))),
            "verified_writes": obj.get("b08_write_verified") is True,
            "experimental_writes": (obj.get("allow_experimental_writes") is True) if override is None else override,
            "write_mode_source": "configuration" if override is None else "session",
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
        raise ValueError("Write zaključan: uključi write mode tipkom u Manageru")
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

def summarize_dhcp_probe(details):
    """Read-only metadata (no IP/MAC/password) for an MQTT diagnostic entity."""
    transport = details.get("transport_probe", {})
    result = next((transport[k] for k in ("get", "post_read")
                  if transport.get(k, {}).get("status") == "field_present_nonempty"), None)
    if result is None:
        result = next((transport[k] for k in ("get", "post_read")
                       if transport.get(k, {}).get("status") == "field_present_empty"), None)
    if result:
        status = "recovered_nonempty" if result["status"] == "field_present_nonempty" else "recovered_empty"
    else:
        status = "unconfirmed"
    return {"status": status, "version": VERSION, "checked_at": int(time()),
            "transport_probe": transport,
            "reservation_field_status": details.get("field_status", {}).get("reservations", {}),
            "dns_field_status": details.get("field_status", {}).get("dhcp_client_dns", {}),
            "errors": details.get("errors", {})}


def publish_dhcp_status(details):
    try:
        publish_probe(summarize_dhcp_probe(details))
    except MQTTProbeError as exc:
        # Reason code contains no network address, broker credential or token.
        print(f"ZTE DHCP MQTT diagnostics unavailable: {str(exc)}", flush=True)
    except Exception as exc:
        # Do not expose broker credentials or error details in the service log.
        print(f"ZTE DHCP MQTT diagnostics unavailable: {type(exc).__name__}", flush=True)


def startup_dhcp_probe():
    # Safe read-only probe once when the app starts; no change to router config.
    threading.Event().wait(6)
    try:
        o = options()
        if not (o.get("mqtt_diagnostics") or o.get("mqtt_startup_probe")):
            return
        with ROUTER_LOCK:
            client = connect(o)
            # Startup: only 2 read endpoint requests, not 20+ slow field probes.
            transport = client.probe_reservation_transport()
        publish_dhcp_status({"transport_probe":transport,"field_status":{},"errors":{}})
    except Exception as exc:
        print(f"ZTE DHCP startup probe unavailable: {type(exc).__name__}", flush=True)
        try:
            publish_probe({"status": "error", "version": VERSION,
                           "reason": type(exc).__name__, "checked_at": int(time())})
        except Exception:
            pass



def startup_dns_option6_probe():
    """Read-only B08 exploration; no ZTE set endpoint is ever invoked."""
    threading.Event().wait(15)
    try:
        o = options()
        # Separate client and bounded read-only probe; do not hold ROUTER_LOCK
        # through slow WebUI static file tests (would block live Ingress UI).
        client = connect(o)
        client.timeout = min(client.timeout, 3)
        version = client.get(["cr_version"]).get("cr_version")
        if version != "CR_A1HRMF297DV1.0.0B08":
            result = {"status":"firmware_mismatch", "option6_verified":False,
                      "firmware_matches":False, "read_only":True}
        else:
            result = probe_dns_option6(client)
            result["firmware_matches"] = True
        result["version"] = VERSION
        publish_dns_probe(result)
    except Exception as exc:
        # Keep errors class-only: no router IP, cookies, credentials or body.
        print(f"ZTE DNS Option6 read-only probe unavailable: {type(exc).__name__}",flush=True)
        try:
            publish_dns_probe({"status":"probe_error", "version":VERSION,
                               "error_type":type(exc).__name__, "option6_verified":False,
                               "read_only":True})
        except Exception:
            pass


def startup_migration_inventory():
    """One-time local MQTT inventory export for AdGuard DHCP migration.

    The MQTT broker is the local HAOS service; no router credentials or
    MAC/IP records are sent to GitHub, logs or external services.
    """
    threading.Event().wait(22)
    try:
        o = options()
        with ROUTER_LOCK:
            client = connect(o)
            inventory = capture_inventory(client)
        inventory["version"] = VERSION
        inventory["checked_at"] = int(time())
        publish_inventory(inventory)
    except Exception as exc:
        print(f"ZTE migration inventory unavailable: {type(exc).__name__}", flush=True)


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
    server_version = "ZTEManager/" + VERSION

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
        static = {"/": ("static/preview.html", "text/html; charset=utf-8"),
                  "/index.html": ("static/preview.html", "text/html; charset=utf-8"),
                  "/demo": ("static/studio.html", "text/html; charset=utf-8"),
                  "/static/network-insights.js": ("static/network-insights.js", "application/javascript; charset=utf-8"),
                  "/static/wifi-draft.js": ("static/wifi-draft.js", "application/javascript; charset=utf-8"),
                  "/static/wifi-control.js": ("static/wifi-control.js", "application/javascript; charset=utf-8"),
                  "/static/preview.js": ("static/preview.js", "application/javascript; charset=utf-8"),
                  "/live": ("static/index.html", "text/html; charset=utf-8"),
                  "/static/studio.js": ("static/studio.js", "application/javascript; charset=utf-8"),
                  "/static/dev-model.js": ("static/dev-model.js", "application/javascript; charset=utf-8"),
                  "/static/studio.css": ("static/studio.css", "text/css; charset=utf-8"),
                  "/static/app.js": ("static/app.js", "application/javascript; charset=utf-8"),
                  "/static/wifi-view.js": ("static/wifi-view.js", "application/javascript; charset=utf-8"),
                  "/static/style.css": ("static/style.css", "text/css; charset=utf-8")}
        if path in static:
            file, mime = static[path]
            return self.response(200, (HERE/file).read_bytes(),mime)
        try:
            o = options()
            if path == "/api/meta":
                return self.response(200, {"version":VERSION,"router_ip":o["ip"],"configured":bool(o["password"]),
                                           "write_mode_source":o["write_mode_source"],"write_enabled":o["write_enabled"],"verified_writes":o["verified_writes"],"experimental_writes":o["experimental_writes"],"disruptive":o["disruptive"],"apn":o["apn"],"wifi_format":o["wifi_format"],"allow_reboot":o["allow_reboot"],"monitor_enabled":o["history"],"monitor_interval_seconds":o["interval"],"csrf":CSRF,
                                           "expected_firmware":o["firmware"]})
            if path == "/api/preview_snapshot":
                with ROUTER_LOCK:
                    result = collect_preview(connect(o))
                result["version"] = VERSION
                return self.response(200, result)
            if path == "/api/wifi_contracts":
                return self.response(200, wifi_contract_catalogue())
            if path == "/api/wifi_source_evidence":
                with ROUTER_LOCK:
                    result = wifi_source(connect(o))
                return self.response(200, result)
            if path == "/api/wifi_getter_source_evidence":
                with ROUTER_LOCK:
                    result = wifi_getter_source(connect(o))
                return self.response(200, result)
            if path == "/api/wifi_original_radio_read":
                with ROUTER_LOCK:
                    result = connect(o).wifi_original_radio_read()
                return self.response(200, result)
            if path == "/api/wifi_original_ap_read":
                with ROUTER_LOCK:
                    result = connect(o).wifi_original_ap_read()
                return self.response(200, result)
            if path == "/api/webui_evidence":
                with ROUTER_LOCK:
                    result = inspect_webui(connect(o))
                return self.response(200, result)
            if path == "/api/webui_wifi_modules":
                with ROUTER_LOCK:
                    result = inspect_wifi_modules(connect(o))
                return self.response(200, result)
            if path == "/api/webui_wifi_channels":
                with ROUTER_LOCK:
                    result = inspect_wifi_channels(connect(o))
                return self.response(200, result)
            if path == "/api/wifi_ui_source_evidence":
                with ROUTER_LOCK:
                    result = wifi_ui_source(connect(o))
                return self.response(200, result)
            if path == "/api/wifi_feature_source_evidence":
                return self.response(200, {'status':'module_selection_required',
                    'modules':list(WIFI_FEATURE_NAMES), 'write_verified':False})
            if path.startswith("/api/wifi_feature_source_evidence/"):
                module_name = path.removeprefix("/api/wifi_feature_source_evidence/")
                if module_name not in WIFI_FEATURE_NAMES:
                    return self.response(404, {'error':'unknown_module'})
                with ROUTER_LOCK:
                    result = wifi_feature_source(connect(o),module_name)
                return self.response(200, result)
            if path == "/api/preview_reservations":
                with ROUTER_LOCK:
                    result = preview_reservations(connect(o))
                return self.response(200, result)
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
            if path == "/api/wifi_details":
                with ROUTER_LOCK:
                    client = connect(o)
                    details = client.wifi_radio_details()
                    try:
                        clients, _ = client.clients()  # station_list stays single-key
                    except RouterError:
                        clients = []
                        details["errors"]["clients"] = "read_unavailable"
                return self.response(200, {**details, "clients": clients})
            if path == "/api/dhcp_details":
                with ROUTER_LOCK:
                    client = connect(o)
                    details = client.dhcp_inventory()
                # One-shot publication is optional and never changes ZTE settings.
                if o.get("mqtt_diagnostics"):
                    threading.Thread(target=publish_dhcp_status, args=(details,), daemon=True).start()
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
        # Serialize mode changes with writes so locking cannot race an apply.
        with ROUTER_LOCK:
            return self.handle_post()

    def handle_post(self):
        global WRITE_OVERRIDE
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
            if self.path == "/api/write_mode":
                enabled = data.get("enabled")
                if type(enabled) is not bool:
                    raise ValueError("enabled mora biti boolean")
                with LOCK:
                    WRITE_OVERRIDE = enabled
                    PLANS.clear()
                    STATIC_PLANS.clear()
                safe_log("write_mode", "enabled" if enabled else "disabled")
                return self.response(200, {"write_enabled": enabled, "experimental_writes": enabled,
                                          "write_mode_source": "session"})
            o = options()
            if self.path in ("/api/static_prepare", "/api/static_apply", "/api/prepare", "/api/apply"):
                if not o["write_enabled"] or not o["experimental_writes"]:
                    raise ValueError("Write zaključan: uključi write mode tipkom u Manageru")
            if self.path == "/api/static_prepare":
                action=str(data.get("action",""))
                values=data.get("values",{})
                if not isinstance(values,dict):raise ValueError("Nevaljana polja rezervacije")
                with ROUTER_LOCK:
                    client=connect(o)
                    groups,errs=client.query_groups(["device","lan","dhcp"])
                    rows=validated_rows(client)
                    prepared=prepare_reservation(action,values,groups,rows)
                    if action == "add":
                        reject_active_ip_collision(client,prepared["mac"],prepared["ip"])
                key=secrets.token_urlsafe(24)
                with LOCK:
                    STATIC_PLANS.clear()
                    STATIC_PLANS[key]={**prepared,"expires":monotonic()+90}
                return self.response(200,{"plan_id":key,"summary":prepared["summary"],
                                          "confirm":prepared["confirm"],"expires_seconds":90,
                                          "warning":"MAC-IP rezervacija bit će promijenjena nakon zasebne potvrde."})
            if self.path == "/api/static_apply":
                key=str(data.get("plan_id",""))
                confirmation=str(data.get("confirmation",""))
                with LOCK:
                    prepared=STATIC_PLANS.pop(key,None)
                if not prepared or prepared["expires"] < monotonic():
                    raise ValueError("Priprema je istekla; ponovi radnju")
                if confirmation!=prepared["confirm"]:
                    raise ValueError("Potvrda nije točna; ništa nije zapisano")
                with ROUTER_LOCK:
                    client=connect(o)
                    groups,errs=client.query_groups(["device","lan","dhcp"])
                    rows=validated_rows(client)
                    if prepared["action"]=="add":
                        reject_active_ip_collision(client,prepared["mac"],prepared["ip"])
                    result=execute_reservation(client,prepared,groups,rows)
                safe_log("static_"+prepared["action"],result["status"])
                return self.response(200,result)
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
    threading.Thread(target=startup_dhcp_probe, name="zte-dhcp-probe", daemon=True).start()
    threading.Thread(target=startup_dns_option6_probe, name="zte-dns-option6-probe", daemon=True).start()
    threading.Thread(target=startup_migration_inventory, name="zte-migration-inventory", daemon=True).start()
    # Passive MQTT command subscriber: exposes a single-use HA diagnostic button.
    # Absolutely no router write occurs until the user presses this button.
    def start_static_test_listener():
        try:
            listen_static_binding_test(lambda: connect(options()))
        except Exception as exc:
            print(f"ZTE static test listener unavailable: {type(exc).__name__}", flush=True)
    threading.Thread(target=start_static_test_listener, name="zte-static-test", daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()

