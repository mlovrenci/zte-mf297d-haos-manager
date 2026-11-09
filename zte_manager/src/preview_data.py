"""Read-only adapters for the new UI. No configuration mutations or MQTT."""
import json
import time
from zte_api import RouterError


def collect(client):
    groups, errors = client.query_groups([
        'device', 'internet', 'signal', 'traffic', 'wifi', 'wifi_extra',
        'lan', 'dhcp', 'dns', 'system_extra'])
    details = client.wifi_radio_details()
    sources = {}
    for name, method in [('wifi', client.clients), ('lan', client.lan_clients)]:
        try:
            value = method(strict=True)
            rows = value[0] if name == 'wifi' else value
            sources[name] = {'status': 'ok', 'rows': rows}
        except (RouterError, ValueError, TypeError):
            sources[name] = {'status': 'unavailable', 'rows': []}
    return {'groups': groups, 'errors': {key: 'read_unavailable' for key in {**errors, **details['errors']}},
            'fields': details['fields'], 'clients': sources['wifi']['rows'],
            'clients_error': sources['wifi']['status'] != 'ok', 'sources': sources,
            'sample_time': int(time.time()), 'write_available': False}


def reservations(client):
    """One known read field; no broad discovery, recovery or write-schema inference."""
    try:
        reply = client.get(['current_static_addr_list'])
        if 'current_static_addr_list' not in reply:
            return {'status': 'unsupported_or_missing', 'rows': [], 'write_available': False}
        raw = reply['current_static_addr_list']
        if raw in ('', None):
            return {'status': 'empty_or_unsupported', 'rows': [], 'write_available': False}
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, list) or any(not isinstance(r, dict) for r in raw):
            raise ValueError('Unexpected reservation schema')
        rows = [{k: str(r[k])[:100] for k in ('hostname', 'name', 'ip_addr', 'ip', 'mac_addr', 'mac')
                 if isinstance(r.get(k), (str, int))} for r in raw[:128]]
        return {'status': 'observed_unverified' if raw else 'empty_or_unsupported',
                'rows': rows, 'truncated': len(raw) > 128, 'write_available': False}
    except (RouterError, ValueError, TypeError):
        return {'status': 'unavailable', 'rows': [], 'write_available': False}
