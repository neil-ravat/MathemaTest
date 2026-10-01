"""Build a local evidence bundle from an explicit allowlist, never secrets/databases."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def package(output):
    files=set()
    for folder in ('src','tests'):
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and p.suffix in {'.py','.json','.lean'} and '__pycache__' not in p.parts)
    # Test utilities import study scripts; include Python sources, never outputs or credentials.
    files.update((ROOT/'scripts').glob('*.py'))
    for name in ['README.md','pyproject.toml','requirements-local.lock.txt',
                 '.github/workflows/python-tests.yml','paper/main.tex',
                 'docs/REPRODUCIBILITY.md','docs/source_manifest.json',
                 'docs/FRESH_EVALUATION_GATE.md','docs/AUDIT_REPAIRS_20260927.md']:
        files.add(ROOT/name)
    files.update((ROOT/'docs/reviews').glob('*.json'))
    for folder in ['artifacts/audit_repairs_20260927','artifacts/extraction_review_set_20260927']:
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and p.suffix in {'.json','.md','.png'} and 'source_snapshot' not in p.parts:
                files.add(p)
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(files): archive.write(p,str(p.relative_to(ROOT)))
        archive.writestr('BUNDLE_MANIFEST.json',json.dumps(dict(files=manifest,
            scope='development evidence; no independent gold; no model weights or PDF included'),indent=2))
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name,digest in manifest.items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==digest
    return len(manifest)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(f'Packaged and verified {package(args.output)} files: {args.output}')
