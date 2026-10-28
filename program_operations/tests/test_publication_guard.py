import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('publication_guard', ROOT / 'program_operations/publication_guard.py')
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
POLICY = json.loads((ROOT / 'docs/publication-policy.json').read_text())


@pytest.mark.parametrize('path', [
    'docs/program/evidence/run/results.json', 'validation/artifacts/V03/run.json',
    '.local-archives/archive.tar.zst', 'archive/old/source.py',
    'docs/program/operations-runs/receipt.json', 'checkpoint.pt',
    'weights.pkl', 'mutation_run.txt', 'coverage.xml',
])
def test_rejects_raw_artifacts_even_when_small(path):
    assert GUARD.check_records([(path, b'x')], POLICY)[0]


def test_rejects_lfs_pointer_disguised_as_text():
    assert GUARD.check_records([('docs/result.md', GUARD.LFS_MAGIC + b'oid sha256:x')], POLICY)[0]


def test_refuses_large_file_and_combined_tree():
    p = dict(POLICY, max_file_bytes=5, max_tree_bytes=7)
    assert GUARD.check_records([('a.py', b'123456')], p)[0]
    assert GUARD.check_records([('a.py', b'1234'), ('b.py', b'1234')], p)[0]


def test_accepts_small_source_summary_and_deterministic_fixture():
    records = [('hponas/a.py', b'pass'), ('docs/results/summary.json', b'{}'),
               ('tests/fixtures/known.npz', b'fixture')]
    assert not GUARD.check_records(records, POLICY)[0]
