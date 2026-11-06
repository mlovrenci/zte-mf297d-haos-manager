"""Offline inventory of original web assets. No network, execution or router writes.

Usage: python tools/audit_b08_assets.py DIRECTORY > evidence.json
Only .js/.html files <= 2 MiB are scanned. Output is a reference inventory,
never proof that a command works on B08. Do not feed HAR or configuration exports.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PATTERNS = {
    'goform_ids': re.compile(r'''goformId\s*[=:]\s*["']([A-Z][A-Z0-9_]{2,79})["']'''),
    'wifi_read_keys': re.compile(r'\bwifi_chip[12]_(?:ssid[12]_)?[a-z_]{2,60}\b'),
}


def analyze(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Expected directory')
    files, skipped = [], 0
    for path in sorted(root.rglob('*')):
        if path.suffix.lower() not in ('.js', '.html') or not path.is_file():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size > 2 * 1024 * 1024 or len(files) >= 500:
            skipped += 1
            continue
        body = path.read_bytes()
        source = body.decode('utf-8', errors='replace')
        files.append({'file': str(path.relative_to(root)), 'sha256': hashlib.sha256(body).hexdigest(),
                      'bytes': len(body), **{name: sorted(set(pattern.findall(source))) for name, pattern in PATTERNS.items()}})
    return {'schema': 1, 'evidence': 'static_reference_only', 'firmware_verified': False,
            'write_verified': False, 'files': files, 'skipped': skipped,
            'next': 'Verify asset provenance, parameter mapping, required fields and readback on the exact firmware.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    print(json.dumps(analyze(args.directory), ensure_ascii=False, indent=2))
