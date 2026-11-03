"""Optional read-only ZTE diagnostics via HAOS MQTT service.

Uses only the Supervisor's MQTT service (mqtt:want). Does NOT grant access
 to Home Assistant's administrator REST API. Never persists broker secrets.
"""
import json
import os
import socket
import ssl
import struct
import time
import urllib.request

class MQTTProbeError(RuntimeError):
    """Non-secret diagnostic reason for MQTT transport failures."""


CONFIG_TOPIC = "homeassistant/sensor/zte_manager_dhcp_probe/config"
STATE_TOPIC = "zte_manager/diag/reservations/state"
ATTRS_TOPIC = "zte_manager/diag/reservations/attributes"


def _enc_len(value):
    out = bytearray()
    while True:
        byte = value % 128
        value //= 128
        if value:
            byte |= 128
        out.append(byte)
        if not value:
            return bytes(out)


def _str(value):
    data = value.encode("utf-8")
    if len(data) > 65535:
        raise ValueError("MQTT value too long")
    return struct.pack("!H", len(data)) + data


def _packet(packet_type, data):
    return bytes((packet_type,)) + _enc_len(len(data)) + data


def _mqtt_publish(service, publications):
    host = str(service["host"])
    port = int(service["port"])
    if not (1 <= port <= 65535):
        raise ValueError("Invalid MQTT port")
    username = service.get("username")
    password = service.get("password")
    flags = 0x02  # Clean session, no will, QoS0
    payload = _str("zte-manager-dhcp-probe")
    if username is not None:
        flags |= 0x80
        payload += _str(str(username))
        if password is not None:
            flags |= 0x40
            payload += _str(str(password))
    header = _str("MQTT") + bytes((4, flags)) + struct.pack("!H", 15)
    with socket.create_connection((host, port), timeout=5) as tcp:
        tcp.settimeout(5)
        if service.get("ssl") is True:
            sock = ssl.create_default_context().wrap_socket(tcp, server_hostname=host)
        else:
            sock = tcp
        # Use same socket lifecycle; avoid exposing secrets in logging.
        with sock if sock is not tcp else _no_close_wrapper(sock) as conn:
            conn.sendall(_packet(0x10, header + payload))
            ack = b""
            while len(ack) < 4:
                fragment = conn.recv(4 - len(ack))
                if not fragment:
                    raise MQTTProbeError("mqtt_connack_missing")
                ack += fragment
            if len(ack) != 4 or ack[:3] != b"\x20\x02\x00" or ack[3] != 0:
                raise MQTTProbeError("mqtt_connection_rejected")
            for topic, body, retain in publications:
                text = json.dumps(body, ensure_ascii=True, separators=(",", ":")) if isinstance(body, (dict, list)) else str(body)
                flags = 0x31 if retain else 0x30
                conn.sendall(_packet(flags, _str(topic) + text.encode("utf-8")))
            conn.sendall(b"\xe0\x00")
            time.sleep(0.15)


class _no_close_wrapper:
    def __init__(self, conn): self.conn = conn
    def __enter__(self): return self.conn
    def __exit__(self, *_): return False


def publish_probe(summary):
    token = os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN", "")
    if not token:
        raise MQTTProbeError("supervisor_token_missing")
    request = urllib.request.Request("http://supervisor/services/mqtt",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as resp:
        payload = json.loads(resp.read(16384).decode("utf-8"))
    service = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not service or not service.get("host") or not service.get("port"):
        raise MQTTProbeError("mqtt_service_unavailable")
    discovery = {
        "name": "ZTE DHCP API probe", "unique_id": "zte_manager_dhcp_probe_v046",
        "state_topic": STATE_TOPIC,
        "json_attributes_topic": ATTRS_TOPIC,
        "entity_category": "diagnostic",
        "icon": "mdi:lan-check",
        "device": {"identifiers": ["zte_manager_mf297d"], "name": "ZTE Manager MF297D"}
    }
    status = str(summary.get("status", "unknown"))[:250]
    _mqtt_publish(service, [(CONFIG_TOPIC, discovery, True),
                            (ATTRS_TOPIC, summary, True),
                            (STATE_TOPIC, status, True)])


# Independent read-only DNS Option 6 investigation entity. This is not a
# configuration control or a claim that DHCP Option 6 can be changed.
DNS_CONFIG_TOPIC = "homeassistant/sensor/zte_manager_dns_option6_probe/config"
DNS_STATE_TOPIC = "zte_manager/diag/dns_option6/state"
DNS_ATTRS_TOPIC = "zte_manager/diag/dns_option6/attributes"


def publish_dns_probe(summary):
    token = os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN", "")
    if not token:
        raise MQTTProbeError("supervisor_token_missing")
    request = urllib.request.Request("http://supervisor/services/mqtt",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as resp:
        data = json.loads(resp.read(16384).decode("utf-8"))
    service = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(service, dict) or not service.get("host") or not service.get("port"):
        raise MQTTProbeError("mqtt_service_unavailable")
    discovery = {
        "name": "ZTE DHCP DNS Option 6 probe",
        "unique_id": "zte_manager_dns_option6_probe_v053",
        "state_topic": DNS_STATE_TOPIC,
        "json_attributes_topic": DNS_ATTRS_TOPIC,
        "entity_category": "diagnostic",
        "icon": "mdi:dns",
        "device": {"identifiers": ["zte_manager_mf297d"], "name": "ZTE Manager MF297D"},
    }
    _mqtt_publish(service, [(DNS_CONFIG_TOPIC, discovery, True),
                            (DNS_ATTRS_TOPIC, summary, True),
                            (DNS_STATE_TOPIC, str(summary.get("status", "unconfirmed"))[:250], True)])