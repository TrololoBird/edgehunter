#!/usr/bin/env python
"""Read-only audit of model artifacts and feature provenance; never unpickles legacy files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def audit(root: str = '.') -> dict:
    base = Path(root).resolve()
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    from core.model_provenance import manifest_path
    from journal import FEATURE_SCHEMA_VERSION

    artifacts = []
    paths = [base / 'pretrained.pkl', *sorted((base / 'models').glob('*.pkl'))]
    for path in paths:
        if not path.exists():
            continue
        item = {'path': str(path.relative_to(base)), 'bytes': path.stat().st_size,
                'manifest': Path(manifest_path(str(path))).exists()}
        if item['manifest']:
            try:
                # Manifest validation reads JSON and hashes the artifact only;
                # the pickle payload is deliberately never loaded here.
                payload = json.loads(Path(manifest_path(str(path))).read_text(encoding='utf-8'))
                item['manifest_logic_version'] = payload.get('logic_version')
                item['manifest_feature_schema'] = payload.get('feature_schema_version')
                item['hash_matches'] = payload.get('artifact_sha256') == __import__('hashlib').sha256(path.read_bytes()).hexdigest()
                if payload.get('quarantine'):
                    item['status'] = 'legacy_quarantined'
            except (OSError, ValueError):
                item['manifest_error'] = True
        else:
            item['status'] = 'legacy_unverified'
        artifacts.append(item)
    unverified = [a['path'] for a in artifacts if a.get('status') == 'legacy_unverified']
    quarantined = [a['path'] for a in artifacts if a.get('status') == 'legacy_quarantined']
    return {'feature_schema_version': FEATURE_SCHEMA_VERSION, 'artifacts': artifacts,
            'legacy_unverified': unverified, 'legacy_quarantined': quarantined,
            'status': 'attention_required' if unverified else 'ok'}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    print(json.dumps(audit(args.root), sort_keys=True))


if __name__ == '__main__':
    main()
