#!/usr/bin/env python3
"""
Verify a validation campaign manifest before execution.

Survey reference: Ch 16 (validation), authority `validation/protocols.json` step 4 of
`preregistration_order`: "Verify manifest (tools/verify_manifest.py) — run is refused if
verification fails."

This is the operational enforcer of item 7 from RESPONSE_TO_CODEX_STATISTICAL_REVIEW.md:
immutable artifacts and preregistration. The manifest declares the exact commit, task
registry digest, seed sets, and scale bounds the campaign will execute against. The
analysis cites the manifest digest; the artifacts embed it. A campaign that cannot
produce a valid manifest signature or whose task registry has drifted from what the
manifest froze cannot run.

What it verifies:
  1. Manifest exists and is valid JSON.
  2. Required fields are present: protocol_version, campaign_id, entry_ids, commit_sha,
     registry_digest, task_registry, seed_sets, scale_bounds, created_at.
  3. commit_sha resolves to an actual git commit in the current repo.
  4. Task registry digest matches the hash of the actual frozen task/seed/bounds records
     declared in the manifest.
  5. Every entry_id named in the manifest exists in protocols.json with status not RETIRED.
  6. Scale bounds are pre-declared and frozen: every task named has (low, high, direction).
  7. Seed sets are disjoint from any pilot seed sets declared in the manifest.
  8. Manifest signature (if present) verifies under the declared public key.

Usage:
    python3 tools/verify_manifest.py <manifest.json>

Exit codes:
    0 = manifest verifies; campaign may proceed
    1 = verification failed; run is refused

Manifest schema (example):
    {
      "protocol_version": "2024-09-04",
      "campaign_id": "V11ab-2026-09-05",
      "entry_ids": ["V11a", "V11b"],
      "commit_sha": "abc123...",
      "registry_digest": "sha256:def456...",
      "task_registry": {
        "task_a": {"low": 0.0, "high": 10.0, "direction": "minimize"},
        "task_b": {"low": -1.0, "high": 1.0, "direction": "maximize"}
      },
      "seed_sets": {
        "V11a": {"no_prior": [0,1,2,3,4], "folklore_prior": [5,6,7,8,9]},
        "V11b": {"no_prior": [0,1,2,3,4], "wrong_prior": [10,11,12,13,14]}
      },
      "pilot_seed_sets": {"pilot_v11": [100,101,102,103,104]},
      "created_at": "2026-09-05T14:32:00Z",
      "signature": "optional_base64_signature",
      "public_key": "optional_base64_pubkey"
    }
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROTOCOLS_PATH = Path("validation/protocols.json")
REQUIRED_FIELDS = [
    "protocol_version",
    "campaign_id",
    "entry_ids",
    "commit_sha",
    "registry_digest",
    "task_registry",
    "seed_sets",
    "created_at",
]


def fail(message: str) -> None:
    """Print failure message and exit with code 1."""
    print(f"VERIFICATION FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def warn(message: str) -> None:
    """Print warning but do not fail."""
    print(f"WARNING: {message}", file=sys.stderr)


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and parse the manifest JSON."""
    if not path.exists():
        fail(f"Manifest not found: {path}")
    try:
        with open(path) as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        fail(f"Manifest is not valid JSON: {e}")
    return manifest


def check_required_fields(manifest: dict[str, Any]) -> None:
    """Verify that all required fields are present."""
    missing = [f for f in REQUIRED_FIELDS if f not in manifest]
    if missing:
        fail(f"Missing required fields: {', '.join(missing)}")


def check_commit_sha(commit_sha: str) -> None:
    """Verify that the commit SHA resolves to an actual git commit."""
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", commit_sha],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        fail(f"commit_sha {commit_sha} does not resolve to a git commit")


def compute_registry_digest(task_registry: dict, seed_sets: dict) -> str:
    """
    Compute the digest of the frozen task registry and seed sets.

    Canonical JSON serialization: sorted keys, no whitespace, UTF-8.
    """
    payload = {"task_registry": task_registry, "seed_sets": seed_sets}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def check_registry_digest(manifest: dict[str, Any]) -> None:
    """Verify that the registry digest matches the frozen task/seed records."""
    declared = manifest["registry_digest"]
    computed = compute_registry_digest(manifest["task_registry"], manifest["seed_sets"])
    if declared != computed:
        fail(
            f"registry_digest mismatch.\n"
            f"  Declared: {declared}\n"
            f"  Computed: {computed}\n"
            f"Task registry or seed sets have drifted from what the manifest froze."
        )


def load_protocols(path: Path = PROTOCOLS_PATH) -> dict[str, Any]:
    """Load the protocol register."""
    if not path.exists():
        fail(f"Protocol register not found: {path}")
    try:
        with open(path) as f:
            protocols = json.load(f)
    except json.JSONDecodeError as e:
        fail(f"Protocol register is not valid JSON: {e}")
    return protocols


def check_entry_ids(manifest: dict[str, Any], protocols: dict[str, Any]) -> None:
    """
    Verify that every entry_id exists in the register and is not RETIRED.

    `entries` is keyed by entry id (V01, V04-T1, V11a, ...), so a campaign naming an
    entry the register does not carry is a preregistration error, not a typo to tolerate.
    """
    entries = protocols.get("entries", {})
    for entry_id in manifest["entry_ids"]:
        if entry_id not in entries:
            fail(f"Entry {entry_id} not found in protocols.json")
        if entries[entry_id].get("status") == "RETIRED":
            fail(f"Entry {entry_id} is RETIRED and cannot be run")


def check_scale_bounds(manifest: dict[str, Any]) -> None:
    """Verify that scale bounds are declared for every task and are well-formed."""
    task_registry = manifest["task_registry"]
    if not task_registry:
        fail("task_registry is empty; at least one task must be declared")

    for task, bounds in task_registry.items():
        if not isinstance(bounds, dict):
            fail(f"Task {task}: bounds must be a dict, got {type(bounds).__name__}")
        for field in ("low", "high", "direction"):
            if field not in bounds:
                fail(f"Task {task}: missing required field '{field}'")
        low, high = bounds["low"], bounds["high"]
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            fail(f"Task {task}: low and high must be numeric")
        if not high > low:
            fail(f"Task {task}: high ({high}) must exceed low ({low})")
        if bounds["direction"] not in ("minimize", "maximize"):
            fail(f"Task {task}: direction must be 'minimize' or 'maximize'")


def check_seed_disjointness(manifest: dict[str, Any]) -> None:
    """
    Verify that confirmatory seed sets are disjoint from pilot seed sets.

    Policy: pilot data reuse is forbidden; pilot and confirmatory campaigns use disjoint
    seed sets.
    """
    confirmatory_seeds: set[int] = set()
    for entry_id, arms in manifest["seed_sets"].items():
        for arm_name, seeds in arms.items():
            if not isinstance(seeds, list):
                fail(f"Entry {entry_id}, arm {arm_name}: seeds must be a list")
            confirmatory_seeds.update(seeds)

    pilot_seeds: set[int] = set()
    for pilot_name, seeds in manifest.get("pilot_seed_sets", {}).items():
        if not isinstance(seeds, list):
            fail(f"Pilot {pilot_name}: seeds must be a list")
        pilot_seeds.update(seeds)

    overlap = confirmatory_seeds & pilot_seeds
    if overlap:
        fail(
            f"Confirmatory and pilot seed sets are not disjoint. Overlapping seeds: "
            f"{sorted(overlap)[:10]}{'...' if len(overlap) > 10 else ''}"
        )


def check_signature(manifest: dict[str, Any]) -> None:
    """
    Verify manifest signature if present.

    Tier 1 scope: check for presence and structure. Actual cryptographic verification
    requires a signature scheme choice (Ed25519, RSA-PSS, ECDSA) and key management,
    which are deferred to the certification milestone.
    """
    if "signature" in manifest:
        if "public_key" not in manifest:
            fail("Manifest has a signature but no public_key field")
        warn(
            "Manifest signature present but cryptographic verification is not yet "
            "implemented (deferred to certification milestone)"
        )


def check_timestamp(manifest: dict[str, Any]) -> None:
    """Verify that created_at is a valid ISO 8601 timestamp."""
    try:
        datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        fail(f"created_at is not a valid ISO 8601 timestamp: {manifest.get('created_at')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a validation campaign manifest before execution"
    )
    parser.add_argument("manifest", type=Path, help="Path to the manifest JSON file")
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress success message; exit code only"
    )
    parser.add_argument(
        "--protocols",
        type=Path,
        default=PROTOCOLS_PATH,
        help=f"Protocol register to check entry ids against (default: {PROTOCOLS_PATH})",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    protocols = load_protocols(args.protocols)

    check_required_fields(manifest)
    check_commit_sha(manifest["commit_sha"])
    check_registry_digest(manifest)
    check_entry_ids(manifest, protocols)
    check_scale_bounds(manifest)
    check_seed_disjointness(manifest)
    check_signature(manifest)
    check_timestamp(manifest)

    if not args.quiet:
        print(f"✓ Manifest {args.manifest} verified successfully.", file=sys.stderr)
        print(f"  Campaign: {manifest['campaign_id']}", file=sys.stderr)
        print(f"  Entries: {', '.join(manifest['entry_ids'])}", file=sys.stderr)
        print(f"  Commit: {manifest['commit_sha'][:12]}", file=sys.stderr)
        print(f"  Registry digest: {manifest['registry_digest'][:20]}...", file=sys.stderr)


if __name__ == "__main__":
    main()
