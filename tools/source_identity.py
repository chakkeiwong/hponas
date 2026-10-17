"""Dependency-free source identity shared by campaigns and program checks."""

import hashlib
import importlib.metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dependency_versions():
    """Re-read the installed runtime manifest; do not cache across execution."""
    return {dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()}


def test_data_paths(root=None):
    """Static non-Python test inputs, with names stable across source copies."""
    root = Path(root) if root is not None else ROOT
    root = root.resolve()
    paths = sorted(path for path in (root / "tests").rglob("*")
                   if path.is_file() and path.suffix != ".py"
                   and not {"__pycache__", ".pytest_cache", ".hypothesis"}.intersection(path.parts))
    if any(not path.resolve().is_relative_to(root) for path in paths):
        raise ValueError("Test data must reside inside the frozen workspace")
    return paths


def source_digest(root=None):
    """Fingerprint code, tests, dependencies and protocols, excluding artifacts.

    Keep this algorithm identical to the original validation.evidence function:
    changing the selection is a provenance decision, not a performance shortcut.
    """
    root = Path(root) if root is not None else ROOT
    paths = []
    for directory in ("hponas", "workloads", "validation", "tools", "tests", "examples"):
        paths.extend((root / directory).rglob("*.py"))
    paths.extend((root / "validation/protocols").glob("*.md"))
    paths += [root / name for name in (
        "pyproject.toml", "requirements.txt", "validation/protocols.json"
    )]
    result = hashlib.sha256()
    for path in sorted(set(paths)):
        if "__pycache__" not in path.parts and "artifacts" not in path.parts:
            result.update(str(path.relative_to(root)).encode() + b"\0"
                          + path.read_bytes() + b"\0")
    return result.hexdigest()
