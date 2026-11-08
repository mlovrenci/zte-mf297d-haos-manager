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

MAX_FILES = 12
MAX_FILE_BYTES = 1048576
MAX_TOTAL_BYTES = 2097152
MAX_SECONDS = 15
COMMANDS = ('SET_WIFI_INFO', 'SET_WIFI_SSID1_SETTINGS', 'SET_WIFI_SSID2_SETTINGS')
PARAMETERS = ('ssid', 'wifiEnabled', 'm_ssid_enable', 'broadcastSsidEnabled',
              'MAX_Access_num', 'security_mode', 'cipher', 'NoForwarding',
              'passphrase', 'wifi_lbd_enable', 'wifi_chip1_channel',
              'wifi_chip2_channel', 'wifi_chip1_bandwidth', 'wifi_chip2_bandwidth')
WIFI_MODULE_SEEDS = (
    '/js/config/menu.js', '/js/router.js', '/js/config/config.js',
    '/js/config/cpe/MF297D/config.js',
    '/js/config/cpe/MF297D/menu_4ggateway.js',
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
        self.main_paths = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'script':
            attrs = dict(attrs)
            for key in ('src', 'data-main'):
                if attrs.get(key):
                    value = attrs[key]
                    if key == 'data-main' and not urllib.parse.urlsplit(value).path.endswith('.js'):
                        value += '.js'
                    self.paths.append(value)
                    if key == 'data-main':
                        self.main_paths.append(value)


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


def module_references(source):
    """Literal AMD dependency arrays only; not an evaluator or complete JS parser."""
    names = []
    for block in re.findall(r'\b(?:require|requirejs|define)\s*\(\s*\[([^\]]{0,8192})\]', source):
        for name in re.findall(r"[\"']([A-Za-z0-9_./-]{1,100})[\"']", block):
            if name not in ('require', 'exports', 'module') and '..' not in name and not name.startswith('/'):
                if name not in names:
                    names.append(name)
    return names[:32]


def wifi_literal_modules(source):
    """Identify literal Wi-Fi module paths from menu/router tables, not runtime data.

    Some stock ZTE menus load their views dynamically, outside AMD dependency
    arrays. A slash is required to avoid treating radio keys as module names.
    """
    names = []
    for name in re.findall(r"[\"']([A-Za-z0-9_./-]{1,100})[\"']", source):
        if '/' not in name or '..' in name or name.startswith('/'):
            continue
        if any(word in name.lower() for word in ('wifi', 'wlan', 'wireless')) and name not in names:
            names.append(name)
        if len(names) >= 32:
            break
    return names


def wifi_relevant_module(name):
    return any(word in name.lower() for word in ('wifi', 'wlan', 'wireless'))


def literal_config(source):
    """Extract bounded literal RequireJS paths; intentionally ignore expressions."""
    base = re.search(r"[\"']?baseUrl[\"']?\s*:\s*[\"']([A-Za-z0-9_./-]+)[\"']", source)
    block = re.search(r"[\"']?paths[\"']?\s*:\s*\{([^}]{0,8192})\}", source)
    aliases = {}
    if block:
        for match in re.finditer(r"(?:[\"']([A-Za-z0-9_/-]+)[\"']|([A-Za-z0-9_]+))\s*:\s*[\"']([A-Za-z0-9_./-]+)[\"']",block.group(1)):
            key = match.group(1) or match.group(2)
            value = match.group(3)
            if '..' not in value and not value.startswith('/'):
                aliases[key] = value
    return {'base_url':base.group(1) if base else None, 'paths':dict(list(aliases.items())[:64])}


def inspect(client, opener=None, clock=time.monotonic, *, wifi_focus=False):
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(client.cookies), NoRedirect())
    start = clock()
    queue = ([client.base + path for path in WIFI_MODULE_SEEDS]
             if wifi_focus else [client.base + '/'])
    module_base = client.base + ('/js/' if wifi_focus else '/')
    aliases = {}
    entry_urls = set()
    visited, files, issues, attempts = set(), [], [], []
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
        attempt = {'path':urllib.parse.urlsplit(url).path, 'status':'pending'}
        attempts.append(attempt)
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
                attempt['status'] = 'read'
                config = literal_config(source) if urllib.parse.urlsplit(url).path.endswith('.js') else {'base_url':None,'paths':{}}
                path = urllib.parse.urlsplit(url).path or '/'
                refs = module_references(source) if path.endswith('.js') else []
                wifi_refs = wifi_literal_modules(source) if wifi_focus and path.endswith('.js') else []
                files.append({'path':path, 'sha256':hashlib.sha256(body).hexdigest(), 'bytes':len(body),
                    'loader_config':config,
                    'module_references':refs,
                    'wifi_literal_modules':wifi_refs,
                    'command_references':[x for x in COMMANDS if re.search(r'\b'+re.escape(x)+r'\b',source)],
                    'parameter_references':[x for x in PARAMETERS if re.search(r'\b'+re.escape(x)+r'\b',source)]})
                if path.endswith('.js'):
                    # Only a literal baseUrl can alter resolution, always constrained to this router.
                    if url in entry_urls and config['base_url']:
                        candidate_base = urllib.parse.urljoin(client.base+'/',config['base_url'].rstrip('/')+'/')
                        if safe_url(client.base,candidate_base,'probe.js'):
                            module_base = candidate_base
                    if url in entry_urls:
                        aliases.update(config['paths'])
                    names = (list(dict.fromkeys(name for name in refs + wifi_refs
                            if wifi_relevant_module(name))) if wifi_focus else refs)
                    for name in names:
                        matching = sorted((key for key in aliases if name == key or name.startswith(key+'/')),key=len,reverse=True)
                        resolved = aliases[matching[0]]+name[len(matching[0]):] if matching else name
                        candidate = safe_url(client.base,module_base,resolved if resolved.endswith(('.js','.html')) else resolved+'.js')
                        if candidate and candidate not in visited and candidate not in queue and len(queue) < MAX_FILES:
                            queue.append(candidate)
                if path == '/' or path.endswith(('.html','.htm')):
                    parser = Scripts()
                    parser.feed(source)
                    for reference in parser.paths:
                        candidate = safe_url(client.base, url, reference)
                        if candidate and reference in parser.main_paths:
                            module_base = candidate.rsplit('/',1)[0]+'/'
                            entry_urls.add(candidate)
                        if candidate and candidate not in visited and candidate not in queue and len(queue) < MAX_FILES:
                            queue.append(candidate)
        except urllib.error.HTTPError as exc:
            attempt['status'] = 'http_'+str(exc.code)
            if exc.code in (301,302,303,307,308):
                candidate = safe_url(client.base, url, exc.headers.get('Location',''))
                if candidate and candidate not in visited and len(queue) < MAX_FILES:
                    queue.append(candidate)
                else:
                    issues.append('redirect_blocked')
            else:
                issues.append('http_error')
        except (OSError, ValueError, urllib.error.URLError):
            attempt['status'] = 'unavailable'
            issues.append('asset_unavailable')
    if queue:
        issues.append('scan_incomplete')
    return {'status':'references_only' if files else 'unavailable', 'files':files,
            'attempts':attempts, 'issues':sorted(set(issues)), 'write_verified':False,
            'scan_scope':'wifi_modules' if wifi_focus else 'entry_assets',
            'limits':{'files':MAX_FILES,'file_bytes':MAX_FILE_BYTES,'seconds':MAX_SECONDS},
            'note':'Static references are not parameter mappings or proof of B08 write support. Dynamic modules may be absent.'}


def inspect_wifi_modules(client, opener=None, clock=time.monotonic):
    """Opt-in bounded GET-only scan of fixed stock Wi-Fi UI module entrypoints."""
    return inspect(client, opener=opener, clock=clock, wifi_focus=True)


SERVICE_SHA256 = '8d5588e3b912827bc09a6380a84f4bef2815b56ce0ad487fdc63c5148c13aaa8'
WIFI_UI_PINNED = {
    '/js/config/menu.js': 'f0802e32266558b16f49ec7c517cbb3248d65f8d2b019dea9b2245bb642ea68c',
    '/js/router.js': 'a5a878ca911a2a5d65160a3a9cf98938e6a9faaba7f50cd25a5e57a2a9daa377',
    '/js/config/config.js': '5bcda613d55ad9d2da687ffe022712d5419856061dcdcd51c6b654f307d99154',
}


def wifi_ui_source(client, opener=None):
    """Return only hash-pinned stock B08 UI scripts for variant route analysis.

    This diagnostic is explicitly invoked, not part of normal preview reads.
    Original static scripts are served verbatim only when exact known hashes
    and firmware match; no user-supplied path or dynamic router data is read.
    """
    groups, errors = client.query_groups(['device'])
    if errors or groups.get('device', {}).get('cr_version') != 'CR_A1HRMF297DV1.0.0B08':
        return {'status': 'firmware_mismatch', 'files': [], 'write_verified': False}
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(client.cookies), NoRedirect())
    files = []
    try:
        for path, expected_sha in WIFI_UI_PINNED.items():
            url = client.base + path
            req = urllib.request.Request(url, method='GET', headers={'Accept-Encoding': 'identity'})
            with opener.open(req, timeout=3) as response:
                if response.geturl() != url or response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                    raise ValueError('Unexpected response')
                body = response.read(65537)
            digest = hashlib.sha256(body).hexdigest()
            if len(body) > 65536 or digest != expected_sha:
                return {'status': 'asset_mismatch', 'files': [], 'write_verified': False}
            files.append({'path': path, 'sha256': digest, 'source': body.decode('utf-8')})
        return {'status': 'pinned_static_source_only', 'files': files, 'write_verified': False}
    except (OSError, UnicodeError, ValueError, urllib.error.URLError):
        return {'status': 'unavailable', 'files': [], 'write_verified': False}


def wifi_source(client, opener=None):
    """Read excerpts only from the previously observed stock B08 service asset.

    This explicitly exposes static source excerpts, never evaluated values.
    Any changed firmware or asset hash fails closed. No caller-controlled path.
    """
    groups, errors = client.query_groups(['device'])
    if errors or groups.get('device', {}).get('cr_version') != 'CR_A1HRMF297DV1.0.0B08':
        return {'status':'firmware_mismatch','excerpts':[], 'write_verified':False}
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(client.cookies), NoRedirect())
    url = client.base + '/js/service.js'
    try:
        req = urllib.request.Request(url, method='GET', headers={'Accept-Encoding':'identity'})
        with opener.open(req, timeout=3) as response:
            if response.geturl() != url:
                raise ValueError('Redirect')
            body = response.read(262145)
            digest = hashlib.sha256(body).hexdigest()
            if len(body) > 262144 or digest != SERVICE_SHA256:
                return {'status':'asset_mismatch','excerpts':[], 'write_verified':False}
        source = body.decode('utf-8')
        excerpts=[]
        for command in COMMANDS:
            for match in list(re.finditer(re.escape(command), source))[:8]:
                start=max(0,match.start()-1800)
                end=min(len(source),match.end()+2800)
                excerpts.append({'command':command,'offset':match.start(),
                                 'start':start,'end':end,'source':source[start:end]})
        return {'status':'static_source_only','sha256':digest,'path':'/js/service.js',
                'excerpts':excerpts,'write_verified':False}
    except (OSError, ValueError, urllib.error.URLError):
        return {'status':'unavailable','excerpts':[], 'write_verified':False}
