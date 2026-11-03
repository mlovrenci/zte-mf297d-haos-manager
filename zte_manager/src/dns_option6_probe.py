"""Read-only exploration of DHCP-advertised DNS (Option 6) on ZTE MF297D B08.

Do not infer DHCP Option 6 from APN/WAN DNS fields, and never send Goform
set commands. Static WebUI assets are scanned for known markers, not executed.
"""
import urllib.error
import urllib.parse
import urllib.request
import gzip
import zlib
import time
from zte_api import RouterError

# ZTE variants expose different names. Unknown keys can be returned as empty.
FIELD_NAMES = (
    'dhcp_dns', 'dhcp_dns1', 'dhcp_dns2', 'dhcp_dns_mode',
    'lan_dns1', 'lan_dns2', 'lan_dns', 'dhcp_primary_dns',
    'dhcp_secondary_dns', 'dhcp_option6_dns', 'dns_relay',
    'dns_proxy_enable', 'dns_primary_dns', 'dns_secondary_dns',
)

# Known ZTE Goform WebUI paths from older and newer device layouts. All are
# fixed, safe GET requests; no user-supplied URL or arbitrary path is accepted.
WEBUI_PATHS = (
    '/js/adm/lan.js', '/tmpl/adm/lan.html', '/js/service.js',
    '/js/adm/router.js', '/js/adm/router_setting.js',
    '/tmpl/adm/router_setting.html', '/js/adm/dhcp.js',
    '/tmpl/adm/dhcp.html', '/js/config/config.js',
)
MARKERS = (
    'dhcp_dns', 'DHCP_DNS_SETTING', 'DHCP_SETTING',
    'ROUTER_DNS_SETTING', 'dhcp_option6', 'lan_dns',
    'dns_relay', 'dns_primary_dns', 'prefer_dns_manual',
)
MAX_BYTES = 350_000


def classify_key_response(field, reply):
    if not isinstance(reply, dict):
        return {'status': 'bad_format'}
    if field not in reply:
        return {'status': 'absent'}
    value = reply[field]
    if value in ('', None, [], {}):
        return {'status': 'empty'}
    if isinstance(value, (dict, list)):
        return {'status': 'returned_complex', 'type': type(value).__name__, 'count': len(value)}
    # IP-like values may be useful diagnostically. Never include credentials.
    return {'status': 'returned_value', 'value': str(value)[:90]}


def probe_goform_fields(client, deadline=None):
    status = {}
    for field in FIELD_NAMES:
        if deadline is not None and time.monotonic() >= deadline:
            status[field] = {'status': 'skipped_time_budget'}
            continue
        try:
            status[field] = classify_key_response(field, client.get([field]))
        except (RouterError, OSError, ValueError):
            status[field] = {'status': 'request_error'}
    return status


def scan_resource_response(raw, content_type, content_encoding):
    if len(raw) > MAX_BYTES:
        return {'status': 'too_large'}
    enc = str(content_encoding or '').lower()
    if enc == 'gzip' or raw.startswith(b'\x1f\x8b'):
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError):
            return {'status': 'unreadable_compressed'}
    elif enc == 'deflate':
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            return {'status': 'unreadable_compressed'}
    if len(raw) > MAX_BYTES:
        return {'status': 'too_large'}
    s = raw.decode('utf-8', errors='replace')
    # No script source is published; only marker presence and response metadata.
    hits = [m for m in MARKERS if m.lower() in s.lower()]
    return {'status': 'read', 'bytes': len(raw),
            'content_type': str(content_type or '').split(';')[0].strip().lower()[:50],
            'markers': hits}


def probe_webui_resources(client, deadline=None):
    result = {}
    for path in WEBUI_PATHS:
        if deadline is not None and time.monotonic() >= deadline:
            result[path] = {'status':'skipped_time_budget'}
            continue
        headers = {'User-Agent': 'ZTE-Manager/DNS-ReadOnly', 'Referer': client.base + '/',
                   'Accept': 'application/javascript, text/javascript, text/html, */*'}
        req = urllib.request.Request(client.base + path, headers=headers, method='GET')
        try:
            with client.opener.open(req, timeout=min(client.timeout, 4)) as resp:
                final = urllib.parse.urlsplit(resp.geturl())
                expected = urllib.parse.urlsplit(client.base)
                if (final.scheme, final.netloc) != (expected.scheme, expected.netloc):
                    result[path] = {'status': 'unexpected_redirect'}
                    continue
                raw = resp.read(MAX_BYTES + 1)
                result[path] = scan_resource_response(
                    raw, resp.headers.get('Content-Type'), resp.headers.get('Content-Encoding'))
        except urllib.error.HTTPError as exc:
            result[path] = {'status': 'http_error', 'http_status': int(exc.code)}
        except (urllib.error.URLError, OSError, TimeoutError):
            result[path] = {'status': 'request_error'}
    return result


def probe_dns_option6(client):
    """A read-only hint report, never definitive proof of DHCP wire Option 6."""
    deadline = time.monotonic() + 35
    fields = probe_goform_fields(client, deadline=deadline)
    webui = probe_webui_resources(client, deadline=deadline)
    has_values = [k for k,v in fields.items() if v.get('status') in ('returned_value', 'returned_complex')]
    matching = [path for path, v in webui.items()
                if v.get('status') == 'read' and any(
                    m.lower() in ('dhcp_dns','dhcp_dns_setting','dhcp_option6','lan_dns','dns_relay')
                    for m in v.get('markers', []))]
    # A returned value / webui marker is evidence for further testing, NOT proof.
    return {'status': 'candidate_found' if (has_values or matching) else 'unconfirmed',
            'option6_verified': False, 'read_only': True,
            'candidate_fields': has_values, 'candidate_webui_paths': matching,
            'fields': fields, 'webui': webui,
            'note': 'WAN DNS settings are NOT DHCP option 6. No DNS/DHCP writes were attempted.'}