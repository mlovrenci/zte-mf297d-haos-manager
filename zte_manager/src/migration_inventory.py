"""Local read-only ZTE inventory for a reviewed AdGuard DHCP migration.

This module must never modify DHCP/DNS or publish a device list outside the
local Home Assistant MQTT broker. Online clients are observations, not leases.
"""
import ipaddress
import json
import os
import re
import urllib.request
from mqtt_probe import _mqtt_publish, MQTTProbeError
from static_reservations import validated_rows

CONFIG_TOPIC = "homeassistant/sensor/zte_manager_migration_inventory/config"
STATE_TOPIC = "zte_manager/migration_inventory/state"
ATTRS_TOPIC = "zte_manager/migration_inventory/attributes"
MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _clean(value, maximum=64):
    return str(value or "").replace("\x00", "").strip()[:maximum]


def normalize_client(row, source):
    if not isinstance(row, dict):
        return None
    mac = _clean(row.get("mac_addr") or row.get("mac"), 24).upper()
    ip = _clean(row.get("ip_addr") or row.get("ip"), 40)
    if not MAC_RE.fullmatch(mac) or mac == "00:00:00:00:00:00":
        return None
    try:
        addr = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        return None
    if not addr.is_private or addr.is_loopback or addr.is_link_local:
        return None
    return {
        "mac": mac, "ip": str(addr),
        "hostname": _clean(row.get("hostname") or row.get("name"), 64),
        "source": source
    }


def capture_inventory(client):
    """Capture static reservations + active stations without any write calls."""
    errors = {}
    try:
        raw_reservations = validated_rows(client)
    except (ValueError, TypeError) as exc:
        raw_reservations = []
        errors["reservations"] = type(exc).__name__
    reservations = []
    for row in raw_reservations[:100]:
        item = normalize_client(row, "zte_reservation")
        if item:
            item["domain"] = _clean(row.get("domain"), 64)
            reservations.append(item)
    online = {}
    for source, collect in (
        ("wifi", lambda: client.clients()[0]),
        ("wired", client.lan_clients),
    ):
        try:
            records = collect()
            if not isinstance(records, list):
                errors[source] = "invalid_response"
                continue
            for row in records[:128]:
                item = normalize_client(row, source)
                if item:
                    key = (item["mac"], item["ip"])
                    online[key] = item
        except Exception as exc:
            errors[source] = type(exc).__name__
    clients = sorted(online.values(), key=lambda x: (x["ip"], x["mac"]))
    reservations.sort(key=lambda x: (x["ip"], x["mac"]))
    return {
        "status": "partial" if errors else "captured",
        "reservations": reservations,
        "observed_clients": clients,
        "reservation_count": len(reservations),
        "observed_count": len(clients),
        "errors": errors,
        "note": "Current observations only: offline DHCP clients may be absent.",
    }


def publish_inventory(info):
    token = os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN", "")
    if not token:
        raise MQTTProbeError("supervisor_token_missing")
    request = urllib.request.Request(
        "http://supervisor/services/mqtt",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        obj = json.loads(response.read(16384).decode("utf-8"))
    svc = obj.get("data") if isinstance(obj.get("data"), dict) else obj
    if not isinstance(svc, dict) or not svc.get("host") or not svc.get("port"):
        raise MQTTProbeError("mqtt_service_unavailable")
    discovery = {
        "name": "ZTE migration inventory",
        "unique_id": "zte_manager_migration_inventory_054",
        "state_topic": STATE_TOPIC,
        "json_attributes_topic": ATTRS_TOPIC,
        "entity_category": "diagnostic",
        "icon": "mdi:lan",
        "device": {"identifiers": ["zte_manager_mf297d"], "name": "ZTE Manager MF297D"},
    }
    # Local HA only; cap snapshot size for MQTT/Recorder stability.
    serialized = json.dumps(info, ensure_ascii=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > 14500:
        raise ValueError("Inventory too large for temporary MQTT sensor")
    _mqtt_publish(svc, [
        (CONFIG_TOPIC, discovery, True),
        (ATTRS_TOPIC, info, True),
        (STATE_TOPIC, info.get("status", "unknown"), True),
    ])
