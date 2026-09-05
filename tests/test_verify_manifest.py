"""
Test tools/verify_manifest.py — the mandatory preregistration verifier.

Survey reference: Ch 16 (validation), `validation/protocols.json` `preregistration_order`
step 4: "Verify manifest (tools/verify_manifest.py) — run is refused if verification
fails." The verifier operationalizes item 7 of RESPONSE_TO_CODEX_STATISTICAL_REVIEW.md
(immutable artifacts and preregistration), whose finding was that the repository had "no
schema or verification tool for the manifest/result pair."

Each test pins one refusal reason. A campaign that can slip past any of them could execute
against a registry that drifted from what was frozen, which is the failure the
preregistration order exists to prevent.
"""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

VERIFIER = "tools/verify_manifest.py"


def canonical_digest(task_registry: dict, seed_sets: dict) -> str:
    """Recompute the registry digest the way the verifier does."""
    payload = {"task_registry": task_registry, "seed_sets": seed_sets}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def reseal(manifest: dict) -> dict:
    """
    Recompute the digest after deliberately editing a manifest.

    Tests that target a check *other* than the digest have to reseal, otherwise the digest
    check fires first and the test proves nothing about the check it names.
    """
    manifest["registry_digest"] = canonical_digest(
        manifest["task_registry"], manifest["seed_sets"]
    )
    return manifest


def head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def valid_manifest() -> dict:
    """A minimal manifest that verifies against the real protocol register."""
    task_registry = {"task_a": {"low": 0.0, "high": 10.0, "direction": "minimize"}}
    seed_sets = {"V11a": {"no_prior": [0, 1, 2], "folklore_prior": [3, 4, 5]}}
    return {
        "protocol_version": "2024-09-04",
        "campaign_id": "test-campaign",
        "entry_ids": ["V11a"],
        "commit_sha": head_sha(),
        "registry_digest": canonical_digest(task_registry, seed_sets),
        "task_registry": task_registry,
        "seed_sets": seed_sets,
        "created_at": "2026-09-05T14:32:00Z",
    }


def run_verify(manifest: dict, *extra_args: str) -> subprocess.CompletedProcess:
    """Write the manifest to a temp file and run the verifier on it."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(manifest, f)
        path = Path(f.name)
    try:
        return subprocess.run(
            ["python", VERIFIER, str(path), *extra_args],
            capture_output=True,
            text=True,
        )
    finally:
        path.unlink()


# ---------------------------------------------------------------------------
# Acceptance
# ---------------------------------------------------------------------------


def test_valid_manifest_verifies():
    result = run_verify(valid_manifest())
    assert result.returncode == 0, result.stderr
    assert "verified successfully" in result.stderr
    assert "V11a" in result.stderr


def test_quiet_mode_is_exit_code_only():
    result = run_verify(valid_manifest(), "--quiet")
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_manifest_without_pilot_seeds_verifies():
    """pilot_seed_sets is optional; its absence is not a refusal."""
    manifest = valid_manifest()
    assert "pilot_seed_sets" not in manifest
    assert run_verify(manifest).returncode == 0


# ---------------------------------------------------------------------------
# Structural refusals
# ---------------------------------------------------------------------------


def test_missing_manifest_file_is_refused():
    result = subprocess.run(
        ["python", VERIFIER, "/nonexistent/manifest.json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Manifest not found" in result.stderr


def test_malformed_json_is_refused():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{not valid json")
        path = Path(f.name)
    try:
        result = subprocess.run(
            ["python", VERIFIER, str(path)], capture_output=True, text=True
        )
        assert result.returncode == 1
        assert "not valid JSON" in result.stderr
    finally:
        path.unlink()


def test_missing_required_field_is_refused():
    manifest = valid_manifest()
    del manifest["commit_sha"]
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "Missing required fields" in result.stderr
    assert "commit_sha" in result.stderr


def test_invalid_timestamp_is_refused():
    manifest = valid_manifest()
    manifest["created_at"] = "not-a-timestamp"
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "not a valid ISO 8601 timestamp" in result.stderr


# ---------------------------------------------------------------------------
# Immutability: commit and registry digest
# ---------------------------------------------------------------------------


def test_unresolvable_commit_is_refused():
    manifest = valid_manifest()
    manifest["commit_sha"] = "0" * 40
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "does not resolve to a git commit" in result.stderr


def test_registry_drift_is_refused():
    """Editing a frozen scale bound after sealing breaks the digest."""
    manifest = valid_manifest()
    manifest["task_registry"]["task_a"]["high"] = 999.0
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "registry_digest mismatch" in result.stderr
    assert "drifted" in result.stderr


def test_seed_set_drift_is_refused():
    """Seed sets are inside the digest, so adding a seed post-seal is caught too."""
    manifest = valid_manifest()
    manifest["seed_sets"]["V11a"]["no_prior"].append(42)
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "registry_digest mismatch" in result.stderr


def test_digest_is_insensitive_to_key_order():
    """
    Canonical JSON means an equivalent manifest seals to the same digest.

    Item 7 of the review flagged exactly this: unspecified canonicalization lets
    equivalent key ordering produce different hashes.
    """
    a = canonical_digest(
        {"t1": {"low": 0.0, "high": 1.0, "direction": "minimize"}},
        {"V11a": {"arm": [1, 2]}},
    )
    b = canonical_digest(
        {"t1": {"direction": "minimize", "high": 1.0, "low": 0.0}},
        {"V11a": {"arm": [1, 2]}},
    )
    assert a == b


# ---------------------------------------------------------------------------
# Entry ids against the register
# ---------------------------------------------------------------------------


def test_unknown_entry_id_is_refused():
    manifest = valid_manifest()
    manifest["entry_ids"].append("V99-NONEXISTENT")
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "not found in protocols.json" in result.stderr


def test_retired_entry_is_refused():
    """A retired entry cannot be run even if a manifest names it."""
    stub = {
        "entries": {
            "V11a": {"id": "V11a", "status": "RETIRED"},
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(stub, f)
        stub_path = Path(f.name)
    try:
        result = run_verify(valid_manifest(), "--protocols", str(stub_path))
        assert result.returncode == 1
        assert "is RETIRED and cannot be run" in result.stderr
    finally:
        stub_path.unlink()


def test_missing_protocol_register_is_refused():
    result = run_verify(valid_manifest(), "--protocols", "/nonexistent/protocols.json")
    assert result.returncode == 1
    assert "Protocol register not found" in result.stderr


# ---------------------------------------------------------------------------
# Frozen scale bounds
# ---------------------------------------------------------------------------


def test_empty_task_registry_is_refused():
    manifest = valid_manifest()
    manifest["task_registry"] = {}
    result = run_verify(reseal(manifest))
    assert result.returncode == 1
    assert "task_registry is empty" in result.stderr


def test_scale_bounds_missing_direction_is_refused():
    manifest = valid_manifest()
    del manifest["task_registry"]["task_a"]["direction"]
    result = run_verify(reseal(manifest))
    assert result.returncode == 1
    assert "missing required field 'direction'" in result.stderr


def test_inverted_scale_bounds_are_refused():
    manifest = valid_manifest()
    manifest["task_registry"]["task_a"].update({"low": 10.0, "high": 0.0})
    result = run_verify(reseal(manifest))
    assert result.returncode == 1
    assert "must exceed" in result.stderr


def test_nonnumeric_scale_bounds_are_refused():
    manifest = valid_manifest()
    manifest["task_registry"]["task_a"]["high"] = "ten"
    result = run_verify(reseal(manifest))
    assert result.returncode == 1
    assert "must be numeric" in result.stderr


def test_unknown_direction_is_refused():
    manifest = valid_manifest()
    manifest["task_registry"]["task_a"]["direction"] = "whatever"
    result = run_verify(reseal(manifest))
    assert result.returncode == 1
    assert "direction must be 'minimize' or 'maximize'" in result.stderr


def test_nondict_bounds_are_refused():
    manifest = valid_manifest()
    manifest["task_registry"]["task_a"] = [0.0, 10.0]
    result = run_verify(reseal(manifest))
    assert result.returncode == 1
    assert "bounds must be a dict" in result.stderr


# ---------------------------------------------------------------------------
# Pilot / confirmatory seed disjointness
# ---------------------------------------------------------------------------


def test_pilot_overlap_is_refused():
    """policy.power.pilot_data_reuse = forbidden, enforced as disjoint seed sets."""
    manifest = valid_manifest()
    manifest["pilot_seed_sets"] = {"pilot_v11": [0, 1, 99]}
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "not disjoint" in result.stderr


def test_disjoint_pilot_seeds_verify():
    manifest = valid_manifest()
    manifest["pilot_seed_sets"] = {"pilot_v11": [100, 101, 102]}
    result = run_verify(manifest)
    assert result.returncode == 0, result.stderr


def test_nonlist_confirmatory_seeds_are_refused():
    manifest = valid_manifest()
    manifest["seed_sets"]["V11a"]["no_prior"] = "0,1,2"
    result = run_verify(reseal(manifest))
    assert result.returncode == 1
    assert "seeds must be a list" in result.stderr


def test_nonlist_pilot_seeds_are_refused():
    manifest = valid_manifest()
    manifest["pilot_seed_sets"] = {"pilot_v11": "100,101"}
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "seeds must be a list" in result.stderr


# ---------------------------------------------------------------------------
# Signature block
# ---------------------------------------------------------------------------


def test_signature_without_public_key_is_refused():
    manifest = valid_manifest()
    manifest["signature"] = "dGVzdF9zaWduYXR1cmU="
    result = run_verify(manifest)
    assert result.returncode == 1
    assert "signature but no public_key" in result.stderr


def test_signature_with_key_warns_but_passes():
    """
    Tier 1 checks the signature block's structure only.

    Choosing a signature scheme and key custody is part of the certification milestone,
    so the verifier says so out loud rather than implying the manifest is authenticated.
    """
    manifest = valid_manifest()
    manifest["signature"] = "dGVzdF9zaWduYXR1cmU="
    manifest["public_key"] = "cHVibGljX2tleV9kdW1teQ=="
    result = run_verify(manifest)
    assert result.returncode == 0
    assert "not yet implemented" in result.stderr
