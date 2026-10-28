"""Reject generated evidence and oversized objects from the publication index."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LFS_MAGIC = b'version https://git-lfs.github.com/spec/v1\n'


def path_error(path, policy):
    if any(path.startswith(p) for p in policy['forbidden_prefixes']):
        return 'raw evidence or local archive path'
    item = PurePosixPath(path)
    fixture = any(path.startswith(p) for p in policy['allowed_binary_fixture_prefixes'])
    if item.suffix in policy['forbidden_suffixes'] and not fixture and path not in policy.get('allowed_documentation_assets', []):
        return 'generated binary artifact'
    if len(item.parts) == 1 and (path == 'coverage.xml' or
            (item.suffix in ('.txt', '.log') and
             any(path.startswith(p) for p in policy['forbidden_root_prefixes']))):
        return 'generated root log'
    return None


def check_records(records, policy):
    errors = []
    total = 0
    for path, data in records:
        reason = path_error(path, policy)
        if reason:
            errors.append(f'{path}: {reason}')
        if data.startswith(LFS_MAGIC):
            errors.append(f'{path}: Git LFS pointer is prohibited')
        if len(data) > policy['max_file_bytes']:
            errors.append(f'{path}: file exceeds publication size limit')
        total += len(data)
    if total > policy['max_tree_bytes']:
        errors.append('Tracked tree exceeds publication size limit')
    return errors, total


def index_records(root):
    rows = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root)
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=root,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for row in rows.split(b'\0'):
            if not row:
                continue
            meta, name = row.split(b'\t', 1)
            mode, oid, stage = meta.split()
            if stage != b'0' or mode not in (b'100644', b'100755', b'120000'):
                raise ValueError('Unmerged or unsupported index entry: ' + name.decode())
            proc.stdin.write(oid + b'\n')
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3 or header[1] != b'blob':
                raise ValueError('Missing index blob')
            data = proc.stdout.read(int(header[2]))
            if proc.stdout.read(1) != b'\n':
                raise ValueError('Invalid Git object framing')
            yield name.decode(), data
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    policy = json.loads((args.root / 'docs/publication-policy.json').read_text())
    records = list(index_records(args.root))
    errors, total = check_records(records, policy)
    print(json.dumps(dict(passed=not errors, files=len(records), tracked_bytes=total,
                          errors=errors[:50]), indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
