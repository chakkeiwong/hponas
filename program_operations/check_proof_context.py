#!/usr/bin/python3 -I
"""Check the real candidate before fixture-only mutation proof regressions."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path('/home/ubuntu/workspace/hponas')


def check(root=ROOT):
    spec = importlib.util.spec_from_file_location(
        'candidate_v03_equivalence', root / 'validation/v03_equivalence.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checker.verify_proof_source_contexts(root)


def main():
    if len(sys.argv) != 1:
        print('This fixed proof preflight accepts no arguments', file=sys.stderr)
        return 2
    check()
    print('Actual candidate mutation proof contexts verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
