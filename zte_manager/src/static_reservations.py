"""B08-verified DHCP static MAC/IP binding operations.

Operations use the original ZTE `DHCP_RESERVATION_ADD` and `_DEL` WebUI
forms, verified on MF297D B08 in 0.5.1 with reversible dummy reservation.
All writes are preceded by a separate prepare+typed-confirmation and fresh
read checks. This module never reboots the router or modifies DHCP pool/DNS.
"""
import hashlib
import ipaddress
import json
import re
from static_binding_test import _read_entries, StaticTestError

MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9_.-]{0,64}$")
FW = "CR_A1HRMF297DV1.0.0B08"


def canonical_mac(mac):
    if not isinstance(mac, str) or not MAC_RE.fullmatch(mac):
        raise ValueError("MAC mora biti u obliku 00:11:22:33:44:55")
    normalized=mac.upper()
    if (int(normalized[:2],16)&1) or normalized == "FF:FF:FF:FF:FF:FF" or normalized == "00:00:00:00:00:00":
        raise ValueError("Multicast/broadcast ili nulti MAC nije dopušten")
    return normalized


def validate_router(groups):
    d=groups.get("device",{});lan=groups.get("lan",{});dhcp=groups.get("dhcp",{})
    if d.get("cr_version") != FW:
        raise ValueError("Potrebno je potvrditi firmware A1 B08")
    if str(dhcp.get("dhcpEnabled")) != "1":
        raise ValueError("DHCP server mora biti uključen")
    try:
        gw=ipaddress.IPv4Address(str(lan.get("lan_ipaddr")))
        network=ipaddress.IPv4Network(str(gw)+"/"+str(lan["lan_netmask"]),strict=False)
        if gw not in network or not gw.is_private:raise ValueError()
    except Exception as exc:
        raise ValueError("Neispravna LAN mreža u ZTE odgovoru") from exc
    return gw,network


def validated_rows(client):
    try:
        entries=_read_entries(client)
    except StaticTestError as exc:
        raise ValueError("Ne mogu pouzdano očitati trenutne rezervacije; write odbijen") from exc
    result=[]
    seen_mac=set();seen_ip=set()
    for record in entries:
        if not isinstance(record,dict):raise ValueError("Neispravan oblik postojećih rezervacija")
        mac=canonical_mac(str(record.get("mac","")))
        try: ip=str(ipaddress.IPv4Address(str(record.get("ip",""))))
        except ValueError as exc: raise ValueError("Neispravna IP adresa u postojećoj listi") from exc
        if mac in seen_mac or ip in seen_ip:
            raise ValueError("Postoje duplikati rezervacija; write blokiran")
        seen_mac.add(mac);seen_ip.add(ip)
        result.append({"mac":mac,"ip":ip,"hostname":str(record.get("hostname", ""))[:100],"domain":str(record.get("domain",""))[:100]})
    return result


def reject_active_ip_collision(client, mac, ip):
    """Block known online devices already using requested IP with another MAC.

    ZTE's station lists can be incomplete; this is a best-effort extra guard,
    not an assertion that an unlisted IP is free.
    """
    try:
        wifi,_ = client.clients()
    except Exception:
        wifi = []
    try:
        lan = client.lan_clients()
    except Exception:
        lan = []
    for device in wifi + lan:
        if str(device.get("ip_addr", "")) != ip:
            continue
        actual=str(device.get("mac_addr", "")).upper()
        if actual and actual != mac.upper():
            raise ValueError("Odabrani IP trenutačno koristi drugi uređaj (druga MAC adresa)")


def fingerprint(rows):
    # Ignores potentially corrupt hostname bytes, uses stable unique MAC/IP pairs.
    pairs=sorted((row["mac"],row["ip"]) for row in rows)
    return hashlib.sha256(json.dumps(pairs,sort_keys=True).encode()).hexdigest()


def prepare(action, values, groups, rows):
    gw,network=validate_router(groups)
    if action not in ("add","delete"):raise ValueError("Nepodržana radnja")
    if action=="add":
        if len(rows)>=10:raise ValueError("ZTE podržava najviše 10 MAC-IP rezervacija")
        mac=canonical_mac(values.get("mac"))
        try:ip=ipaddress.IPv4Address(str(values.get("ip","")))
        except ValueError as exc:raise ValueError("Nevaljana IPv4 adresa") from exc
        if ip not in network or ip in (gw,network.network_address,network.broadcast_address):
            raise ValueError("Rezervirana IP adresa mora biti LAN klijent, ne gateway/broadcast")
        if any(r["mac"]==mac or r["ip"]==str(ip) for r in rows):
            raise ValueError("MAC ili IP već je rezerviran")
        name=str(values.get("hostname","")).strip()
        domain=str(values.get("domain","")).strip()
        if not NAME_RE.fullmatch(name):raise ValueError("Naziv 1–32 znaka, slova/brojevi/_/-")
        if not DOMAIN_RE.fullmatch(domain):raise ValueError("Nevaljana lokalna domena")
        params={"host_name":name,"mac_addr":mac,"ip_addr":str(ip),"domain":domain}
        summary=f"Dodaj MAC-IP rezervaciju: {name}, {mac} → {ip}. DHCP ostaje uključen; bez restarta."
        confirm="DODAJ_REZERVACIJU"
    else:
        mac=canonical_mac(values.get("mac"))
        match=next((r for r in rows if r["mac"]==mac),None)
        if not match:raise ValueError("Odabrana rezervacija ne postoji; osvježi listu")
        params={"mac_addr":mac+";"}
        summary=f"TRAJNO OBRIŠI rezervaciju {mac} → {match['ip']}. Uređaj može dobiti drugu IP adresu nakon obnavljanja DHCP leasea."
        confirm="OBRISI_REZERVACIJU"
    return {"action":action,"params":params,"summary":summary,"confirm":confirm,"mac":mac,
            "ip":str(ip) if action=="add" else match["ip"],"before_fingerprint":fingerprint(rows),
            "before_count":len(rows)}


def execute(client, plan, groups, rows):
    validate_router(groups)
    if fingerprint(rows)!=plan["before_fingerprint"]:
        raise ValueError("Lista rezervacija promijenila se nakon pripreme; ponovi postupak")
    if plan["action"]=="add":
        current=prepare("add",{"mac":plan["mac"],"ip":plan["ip"],"hostname":plan["params"]["host_name"],"domain":plan["params"]["domain"]},groups,rows)
        command="DHCP_RESERVATION_ADD"
    elif plan["action"]=="delete":
        current=prepare("delete",{"mac":plan["mac"]},groups,rows)
        command="DHCP_RESERVATION_DEL"
    else:raise ValueError("Nedopuštena radnja")
    if current["params"]!=plan["params"]:raise ValueError("Rezervacija se promijenila")
    request={"isTest":"false", "goformId":command, **plan["params"],"AD":client._ad()}
    accepted=False;send_error=None
    try:
        reply=client._request("/goform/goform_set_cmd_process",request)
        accepted=str(reply.get("result","")).lower() in ("success","0")
        if not accepted:send_error="Router nije potvrdio operaciju"
    except Exception as exc:
        send_error=type(exc).__name__
    try:
        after=validated_rows(client)
    except Exception as exc:
        return {"status":"uncertain","accepted":accepted,"error":send_error,
                "read_error_type":type(exc).__name__,"note":"Provjera nakon upisa nije uspjela; ne ponavljaj radnju bez pregleda liste."}
    exists=any(r["mac"]==plan["mac"] and r["ip"]==plan["ip"] for r in after)
    confirmed=exists if plan["action"]=="add" else not exists
    return {"status":"verified" if confirmed else "uncertain","accepted":accepted,
            "confirmed":confirmed,"before_count":plan["before_count"],"after_count":len(after),
            "error":send_error,"note":"Provjera rezervacija uspješna" if confirmed else "Upis nije potvrđen; ponovno očitaj listu prije ponavljanja."}