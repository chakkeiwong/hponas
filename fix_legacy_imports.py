#!/usr/bin/env python3
"""Update imports from hponas.searchers/executors to legacy versions."""

import re
import sys
from pathlib import Path

def fix_imports(file_path):
    """Fix imports in a single file."""
    content = file_path.read_text()
    original = content

    # Fix searchers imports
    content = re.sub(
        r'from hponas\.searchers import',
        'from hponas.legacy_searchers import',
        content
    )

    # Fix executors imports
    content = re.sub(
        r'from hponas\.executors import',
        'from hponas.legacy_executors import',
        content
    )

    if content != original:
        file_path.write_text(content)
        return True
    return False

def main():
    root = Path(__file__).parent
    tests_dir = root / "tests"

    updated = []
    for py_file in tests_dir.rglob("*.py"):
        if fix_imports(py_file):
            updated.append(py_file.relative_to(root))

    if updated:
        print(f"Updated {len(updated)} files:")
        for f in updated:
            print(f"  {f}")
    else:
        print("No files needed updating")

if __name__ == "__main__":
    main()
