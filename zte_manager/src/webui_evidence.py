"""Bounded GET-only inventory of static assets served by the configured router.

Never executes JavaScript, follows external URLs, accepts user-supplied paths,
reads configuration exports, or returns raw asset contents/cookies.
"""
import hashlib
from html.parser import HTMLParser
import re
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_FILES = 8
MAX_FILE_BYTES = 262144
MAX_TOTAL_BYTES = 1048576
MAX_SECONDS = 15
COMMANDS = ('SET_WIFI_INFO', 'SET_WIFI_SSID1_SETTINGS', 'SET_WIFI_SSID2_SETTINGS')
PARAMETERS = ('ssid', 'wifiEnabled', 'm_ssid_enable', 'broadcastSsidEnabled',
              'MAX_Access_num', 'security_mode', 'cipher', 'NoForwarding',
              'passphrase', 'wifi_lbd_enable', 'wifi_chip1_channel',
              'wifi_chip2_channel', 'wifi_chip1_bandwidth', 'wifi_chip2_bandwidth')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'script':
            attrs = dict(attrs)
            for key in ('src', 'data-main'):
                if attrs.get(key):
                    value = attrs[key]
                    if key == 'data-main' and not urllib.parse.urlsplit(value).path.endswith('.js'):
                        value += '.js'
                    self.paths.append(value)


def safe_url(base, parent, reference):
    """Only root and literal same-origin HTML/JS assets; never Goform endpoints."""
    if not isinstance(reference, str) or len(reference) > 256 or any(c in reference for c in ('\\', '%', '\r', '\n')):
        return None
    u = urllib.parse.urlsplit(urllib.parse.urljoin(parent, reference))
    origin = urllib.parse.urlsplit(base)
    if u.scheme != origin.scheme or u.netloc != origin.netloc or u.username or u.password:
        return None
    path = u.path or '/'
    if not re.fullmatch(r'/[A-Za-z0-9_./-]*', path) or '..' in path or '/goform' in path.lower():
        return None
    if path != '/' and not path.lower().endswith(('.html', '.htm', '.js')):
        return None
    return urllib.parse.urlunsplit((u.scheme, u.netloc, path, '', ''))


def inspect(client, opener=None, clock=time.monotonic):
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(client.cookies), NoRedirect())
    start = clock()
    queue = [client.base + '/']
    visited, files, issues = set(), [], []
    total = 0
    while queue and len(visited) < MAX_FILES and total < MAX_TOTAL_BYTES:
        remaining = MAX_SECONDS - (clock() - start)
        if remaining <= 0:
            issues.append('time_limit')
            break
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        request = urllib.request.Request(url, method='GET', headers={'Accept-Encoding':'identity', 'Accept':'text/html, application/javascript, text/javascript'})
        try:
            with opener.open(request, timeout=min(3, remaining)) as response:
                if response.geturl() != url:
                    issues.append('unexpected_redirect')
                    continue
                if response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                    issues.append('compressed_asset_skipped')
                    continue
                limit = min(MAX_FILE_BYTES, MAX_TOTAL_BYTES-total)
                body = response.read(limit+1)
                total += len(body)
                if len(body) > limit:
                    issues.append('size_limit')
                    continue
                source = body.decode('utf-8', errors='replace')
                path = urllib.parse.urlsplit(url).path or '/'
                files.append({'path':path, 'sha256':hashlib.sha256(body).hexdigest(), 'bytes':len(body),
                    'command_references':[x for x in COMMANDS if re.search(r'\b'+re.escape(x)+r'\b',source)],
                    'parameter_references':[x for x in PARAMETERS if re.search(r'\b'+re.escape(x)+r'\b',source)]})
                if path == '/' or path.endswith(('.html','.htm')):
                    parser = Scripts()
                    parser.feed(source)
                    for reference in parser.paths:
                        candidate = safe_url(client.base, url, reference)
                        if candidate and candidate not in visited and candidate not in queue and len(queue) < MAX_FILES:
                            queue.append(candidate)
        except urllib.error.HTTPError as exc:
            if exc.code in (301,302,303,307,308):
                candidate = safe_url(client.base, url, exc.headers.get('Location',''))
                if candidate and candidate not in visited and len(queue) < MAX_FILES:
                    queue.append(candidate)
                else:
                    issues.append('redirect_blocked')
            else:
                issues.append('http_error')
        except (OSError, ValueError, urllib.error.URLError):
            issues.append('asset_unavailable')
    if queue:
        issues.append('scan_incomplete')
    return {'status':'references_only' if files else 'unavailable', 'files':files,
            'issues':sorted(set(issues)), 'write_verified':False,
            'limits':{'files':MAX_FILES,'file_bytes':MAX_FILE_BYTES,'seconds':MAX_SECONDS},
            'note':'Static references are not parameter mappings or proof of B08 write support. Dynamic modules may be absent.'}
