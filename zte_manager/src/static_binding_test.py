"""One-time, user-triggered, fixed-scope DHCP binding test for A1 MF297D B08.

No general-purpose write RPC. The test reserves only an offline locally
administered MAC at .254 (outside the observed DHCP pool), verifies the row,
then deletes just this row. It never changes DHCP/WAN/WiFi settings.
"""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import struct
import time
import urllib.request

from mqtt_probe import _str, _packet, _mqtt_publish

MAC = "02:5A:54:45:00:FE"  # local/unicast; never a real hardware MAC
IP = "192.168.1.254"    # outside observed DHCP pool 192.168.1.2-.253
HOSTNAME = "ZTE-MGR-TEST"
TOPIC = "zte_manager/test_static_binding/command"
STATE = "zte_manager/test_static_binding/state"
ATTRS = "zte_manager/test_static_binding/attributes"
BUTTON_CONFIG = "homeassistant/button/zte_manager_static_binding_test/config"
SENSOR_CONFIG = "homeassistant/sensor/zte_manager_static_binding_test/config"
MARKER = Path("/data/zte_static_binding_test_051.json")


class StaticTestError(RuntimeError):
    pass


def _mqtt_service():
    token = os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN", "")
    if not token:
        raise StaticTestError("Supervisor token unavailable")
    request = urllib.request.Request("http://supervisor/services/mqtt",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=6) as resp:
        obj = json.loads(resp.read(16384).decode("utf-8"))
    svc = obj.get("data") if isinstance(obj.get("data"), dict) else obj
    if not isinstance(svc, dict) or not svc.get("host") or not svc.get("port"):
        raise StaticTestError("MQTT service unavailable")
    return svc


def _read_exact(sock, length):
    data = bytearray()
    while len(data) < length:
        c = sock.recv(length - len(data))
        if not c:
            raise StaticTestError("MQTT connection closed")
        data.extend(c)
    return bytes(data)


def _recv_packet(sock):
    first = _read_exact(sock, 1)[0]
    remaining = 0
    shift = 0
    for _ in range(4):
        byte = _read_exact(sock, 1)[0]
        remaining |= (byte & 127) << shift
        if not byte & 128:
            break
        shift += 7
    else:
        raise StaticTestError("Invalid MQTT length")
    if remaining > 16384:
        raise StaticTestError("MQTT packet too large")
    return first, _read_exact(sock, remaining)


def _subscribe(service):
    sock = socket.create_connection((str(service["host"]), int(service["port"])), timeout=6)
    sock.settimeout(6)
    if service.get("ssl") is True:
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=service["host"])
    flags = 0x02
    identity = "zte-static-" + secrets.token_hex(5)
    data = _str(identity)
    if service.get("username") is not None:
        flags |= 0x80
        data += _str(str(service["username"]))
        if service.get("password") is not None:
            flags |= 0x40
            data += _str(str(service["password"]))
    connect = _str("MQTT") + bytes((4, flags)) + struct.pack("!H", 45) + data
    sock.sendall(_packet(0x10, connect))
    kind, ack = _recv_packet(sock)
    if kind != 0x20 or ack != b"\x00\x00":
        sock.close()
        raise StaticTestError("MQTT CONNECT rejected")
    sock.sendall(_packet(0x82, b"\x00\x01" + _str(TOPIC) + b"\x00"))
    kind, ack = _recv_packet(sock)
    if kind != 0x90 or len(ack) < 3 or ack[2] == 0x80:
        sock.close()
        raise StaticTestError("MQTT SUBSCRIBE rejected")
    return sock


def _publish(service, state, attrs):
    payload = {"status":state, "version":"0.5.1", **attrs}
    _mqtt_publish(service, [(ATTRS, payload, True), (STATE, state, True)])


def _read_entries(router):
    reply = router.probe_reservation_transport(include_records=True)
    for name in ("get", "post_read"):
        x = reply.get(name, {})
        if x.get("status") == "field_present_empty" and x.get("value_type") == "list":
            return []
        if x.get("status") != "field_present_nonempty" or x.get("value_type") != "list":
            continue
        records = x.get("records")
        if isinstance(records, list) and len(records) == x.get("list_length") and all(isinstance(y,dict) for y in records):
            return records
    raise StaticTestError("Unable to read complete static binding list")


def _validate_preconditions(router, groups, rows):
    dev, lan, dhcp = (groups.get(k,{}) for k in ("device","lan","dhcp"))
    if dev.get("cr_version") != "CR_A1HRMF297DV1.0.0B08":
        raise StaticTestError("Firmware B08 mismatch")
    if lan.get("lan_ipaddr") != "192.168.1.1" or lan.get("lan_netmask") != "255.255.255.0":
        raise StaticTestError("Unexpected LAN network")
    if str(dhcp.get("dhcpEnabled")) != "1" or dhcp.get("dhcpStart") != "192.168.1.2" or dhcp.get("dhcpEnd") != "192.168.1.253":
        raise StaticTestError("Unexpected DHCP configuration")
    if not 0 <= len(rows) < 10:
        raise StaticTestError("Reservation capacity check failed")
    for row in rows:
        ip = str(row.get("ip", ""))
        mac = str(row.get("mac", ""))
        if ip == IP or mac.lower() == MAC.lower():
            raise StaticTestError("Test IP/MAC already bound, do not overwrite")
        try:
            ipaddress.IPv4Address(ip)
        except ValueError:
            raise StaticTestError("Existing list has invalid IP, abort")
    return True


def _send_binding(router, operation):
    # Exact ZTE original WebUI write parameters, no user-supplied values.
    if operation == "add":
        params = {"goformId":"DHCP_RESERVATION_ADD", "host_name":HOSTNAME,
                  "mac_addr":MAC, "ip_addr":IP, "domain":""}
    elif operation == "delete":
        params = {"goformId":"DHCP_RESERVATION_DEL", "mac_addr":MAC+";"}
    else:
        raise ValueError("Unsupported operation")
    response = router._request("/goform/goform_set_cmd_process",
                               {"isTest":"false", **params, "AD":router._ad()})
    if str(response.get("result", "")).lower() not in ("success","0"):
        raise StaticTestError("ZTE rejected "+operation)
    return True


def _contains(rows):
    return any(str(r.get("mac", "")).lower() == MAC.lower() and str(r.get("ip", "")) == IP for r in rows)


def run_binding_test(router_factory, marker=MARKER):
    """Always attempt to delete the test row if it is observed after add."""
    if marker.exists():
        raise StaticTestError("Test already executed; no re-run")
    # Mark BEFORE any mutation, making process crash/restart non-reentrant.
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"status":"started", "at":int(time.time())}))
    report={"test_mac":MAC,"test_ip":IP,"attempted_add":False,
            "add_accepted":False,"observed_after_add":False,
            "attempted_delete":False,"removed":False}
    try:
        router=router_factory()
        groups,errors=router.query_groups(["device","lan","dhcp"])
        before=_read_entries(router)
        report["before_count"]=len(before)
        _validate_preconditions(router,groups,before)
        report["attempted_add"]=True
        try:
            _send_binding(router,"add")
            report["add_accepted"]=True
        except Exception as exc:
            report["add_error_type"]=type(exc).__name__
        # Router may have applied mutation even if response was malformed.
        try:
            after=_read_entries(router)
            report["after_add_count"]=len(after)
            report["observed_after_add"]=_contains(after)
        except Exception as exc:
            report["read_after_error_type"]=type(exc).__name__
        # Only delete this exact dummy MAC. Never touch any other entry.
        if report["observed_after_add"] or report["add_accepted"]:
            report["attempted_delete"]=True
            try:
                _send_binding(router,"delete")
                report["delete_accepted"]=True
            except Exception as exc:
                report["delete_error_type"]=type(exc).__name__
            try:
                final=_read_entries(router)
                report["final_count"]=len(final)
                report["removed"]=not _contains(final)
            except Exception as exc:
                report["read_final_error_type"]=type(exc).__name__
        status=("passed" if report["observed_after_add"] and report["removed"]
                else "cleanup_needed" if report["observed_after_add"] and not report["removed"]
                else "not_confirmed")
    except Exception as exc:
        status="aborted"
        report["error_type"]=type(exc).__name__
        report["error_message"]=str(exc)[:160]
    report["status"]=status
    marker.write_text(json.dumps(report,ensure_ascii=True))
    return report


def _device():
    return {"identifiers":["zte_manager_mf297d"],"name":"ZTE Manager MF297D"}


def listen_once(router_factory, status_callback=None):
    """Expose a one-time MQTT button. No router write before a button press."""
    service=_mqtt_service()
    nonce=secrets.token_urlsafe(26)
    if MARKER.exists():
        try: _publish(service,"already_executed",json.loads(MARKER.read_text()))
        except (ValueError,OSError): pass
        return
    sock=_subscribe(service)
    try:
        _mqtt_publish(service, [
          (SENSOR_CONFIG,{"name":"ZTE static binding test", "unique_id":"zte_manager_static_binding_test_v051",
                          "state_topic":STATE,"json_attributes_topic":ATTRS,
                          "entity_category":"diagnostic", "device":_device()}, True),
          (BUTTON_CONFIG,{"name":"Run ZTE static binding test once", "unique_id":"zte_manager_run_static_test_v051",
                          "command_topic":TOPIC,"payload_press":nonce,
                          "entity_category":"diagnostic", "device":_device()},True)
        ])
        _publish(service,"ready",{"test_ip":IP,"test_mac":MAC,"safe_scope":"dummy_binding_only"})
        expires=time.monotonic()+1200
        last_ping=time.monotonic()
        sock.settimeout(2)
        while time.monotonic()<expires:
            try: kind, payload=_recv_packet(sock)
            except socket.timeout:
                if time.monotonic()-last_ping>18:
                    sock.sendall(b"\xc0\x00")
                    last_ping=time.monotonic()
                continue
            if kind>>4!=3:
                continue
            if len(payload)<2: continue
            n=struct.unpack("!H",payload[:2])[0]
            if n>len(payload)-2: continue
            topic=payload[2:2+n].decode("utf-8","replace")
            message=payload[2+n:].decode("utf-8","replace")
            if topic!=TOPIC or message!=nonce: continue
            _publish(service,"running",{"test_ip":IP,"test_mac":MAC})
            result=run_binding_test(router_factory)
            _publish(service,result["status"],result)
            # One-time; remove the button so it cannot be pressed again.
            _mqtt_publish(service,[(BUTTON_CONFIG,"",True)])
            return
        _publish(service,"expired",{"reason":"button_not_pressed"})
    finally:
        try: sock.close()
        except OSError:pass