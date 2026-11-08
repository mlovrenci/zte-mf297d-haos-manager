"""Offline HAR inspection. Never sends requests or exports response values/secrets."""
import argparse
import base64
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'zte_manager/src'))
from zte_api import GROUPS, WIFI_DETAIL_PROBES

SAFE_KEYS = frozenset(k for group in ('wifi', 'wifi_extra') for k in GROUPS[group]) | frozenset(
    k for keys in WIFI_DETAIL_PROBES.values() for k in keys)
MAX_BYTES = 20 * 1024 * 1024


def analyze(har):
    entries = har.get('log', {}).get('entries')
    if not isinstance(entries, list) or len(entries) > 10000:
        raise ValueError('Invalid HAR entries or entry limit exceeded')
    reads = []
    ignored = 0
    for entry in entries:
        request = entry.get('request', {})
        url = urlsplit(request.get('url', ''))
        if request.get('method') != 'GET' or url.path != '/goform/goform_get_cmd_process':
            ignored += 1
            continue
        query = parse_qs(url.query)
        commands = query.get('cmd', [''])[0].split(',')
        keys = [k for k in commands if k in SAFE_KEYS]
        if not keys:
            ignored += 1
            continue
        response = entry.get('response', {})
        content = response.get('content', {})
        raw = content.get('text', '')
        parsed = None
        try:
            if len(raw) > 1048576:
                raise ValueError('Oversized body')
            if content.get('encoding') == 'base64':
                raw = base64.b64decode(raw, validate=True).decode('utf-8')
            parsed = json.loads(raw)
        except (ValueError, TypeError, UnicodeError):
            pass
        reads.append({'method':'GET','path':'/goform/goform_get_cmd_process',
                      'keys':keys,'omitted_key_count':len(commands)-len(keys),
                      'multi_data':query.get('multi_data') == ['1'],
                      'status':response.get('status') if isinstance(response.get('status'), int) else None,
                      'response_shape':'object' if isinstance(parsed, dict) else 'unavailable_or_non_object',
                      'fields':{k: ('missing' if not isinstance(parsed, dict) or k not in parsed else
                                    'empty' if parsed[k] in (None, '') else 'present') for k in keys}})
    return {'format':'zte-wifi-har-review-v1','offline_only':True,'sendable':False,
            'reads':reads,'ignored_entries':ignored,
            'note':'Values, origins, cookies, credentials and request bodies are never exported. This is not an executable replay.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('har', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.har.resolve() == args.output.resolve():
        parser.error('Output must differ from input')
    if args.har.stat().st_size > MAX_BYTES:
        parser.error('HAR exceeds 20 MiB limit')
    result = analyze(json.loads(args.har.read_text(encoding='utf-8-sig')))
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
