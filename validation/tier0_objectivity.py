"""Computable obligations, distinct from human approval and resource permission.

Selection replay establishes consistency of supplied records. It cannot prove
that a history is complete, a seed was concealed, or two executions independent.
Those unresolved evidence producers/verifiers stay explicit campaign blockers.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


SELECTION_ALGORITHM = "sha256_seed_nul_task_stratified_v1"
OBJECTIVE_POLICY = {
    "decision": "D-OBJECTIVE-EVIDENCE",
    "scientific_result": "recomputed_from_frozen_rules_and_bound_raw_evidence",
    "human_scientific_override": False,
    "reviewer_identity_required": False,
    "unknown_assumptions": "unresolved_never_approved_into_passing",
    "resource_authorization": "separate_no_scientific_effect",
}
SAMPLING_OPEN_OBLIGATIONS = (
    "STAT-03/D: exposure-history coverage and lineage eligibility remain unsupported beyond the reconstructed local scope",
    "STAT-03/D: independently anchored commit/freeze/reveal chronology and seed isolation remain unverified",
    "STAT-03/F: execution-isolation contract and actual campaign evidence remain unfrozen; fresh-process checks do not prove stochastic independence",
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _hex_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ValueError(f"Nonfinite JSON: {value}")


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        _reject_nonfinite(value)
    return parsed


def read_bound_json(root, ref):
    """Read an exact repository-local snapshot, refusing aliases/ambiguous JSON."""
    if (not isinstance(ref, dict) or set(ref) != {"path", "sha256"}
            or not isinstance(ref["path"], str) or not ref["path"] or not _hex_digest(ref["sha256"])):
        raise ValueError("Missing or malformed bound JSON reference")
    relative = Path(ref["path"])
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root):
        raise ValueError("Evidence must stay within the repository")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Changed bound JSON evidence")
    result = json.loads(raw, object_pairs_hook=_unique_object,
                        parse_constant=_reject_nonfinite, parse_float=_finite_float)
    if not isinstance(result, dict):
        raise ValueError("Evidence must be a JSON object")
    return result


def replay_selection(ledger, manifest):
    """Recompute committed stratified sampling; never attest physical provenance.

    Even 'documented_unexposed' is only an input assertion at this stage. A
    consistent replay is explicitly INCONCLUSIVE until provenance is verified.
    No reviewer, signature, approval or declared PASS field is consulted.
    """
    if (ledger.get("kind") != "tier0_exposure_ledger_v1"
            or manifest.get("kind") != "tier0_selection_manifest_v1"
            or manifest.get("algorithm") != SELECTION_ALGORITHM):
        raise ValueError("Unknown exposure ledger or selection contract")
    if manifest.get("ledger_digest") != _digest(ledger):
        raise ValueError("Selection does not bind the exact exposure ledger")
    seed_hex = manifest.get("seed_reveal")
    if not _hex_digest(seed_hex):
        raise ValueError("Selection requires exactly 32 revealed seed bytes")
    seed = bytes.fromhex(seed_hex)
    if hashlib.sha256(seed).hexdigest() != manifest.get("seed_commitment"):
        raise ValueError("Selection seed differs from its commitment")
    frame = ledger.get("frame")
    if not isinstance(frame, list) or not frame:
        raise ValueError("Selection requires a nonempty exposure frame")
    strata, seen = {}, set()
    for row in frame:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]
                or not isinstance(row.get("stratum"), str) or not row["stratum"]
                or row.get("exposure") not in {"documented_unexposed", "exposed", "unknown"}):
            raise ValueError("Malformed exposure frame row")
        if row["id"] in seen:
            raise ValueError("Duplicate task in exposure frame")
        seen.add(row["id"])
        strata.setdefault(row["stratum"], [])
        if row["exposure"] == "documented_unexposed":
            strata[row["stratum"]].append(row["id"])
    counts = manifest.get("counts")
    if not isinstance(counts, dict) or set(counts) != {"V04-T0", "V05"}:
        raise ValueError("Selection requires frozen counts for both entries")
    selected = {}
    for entry, requested in counts.items():
        if not isinstance(requested, dict) or set(requested) != set(strata):
            raise ValueError("Selection counts must cover the exact strata")
        selected[entry] = []
        for stratum, count in sorted(requested.items()):
            candidates = strata[stratum]
            if type(count) is not int or not 0 <= count <= len(candidates):
                raise ValueError("Invalid count or insufficient documented eligible tasks")
            ranking = sorted(candidates, key=lambda tid: (
                hashlib.sha256(seed + b"\0" + tid.encode("utf-8")).digest(), tid,
            ))
            selected[entry].extend(ranking[:count])
        if not selected[entry]:
            raise ValueError("Each entry requires a nonempty selection")
    if manifest.get("entry_tasks") != selected:
        raise ValueError("Declared tasks differ from recomputed committed selection")
    return {"selection_reproduced": True, "entry_tasks": selected,
            "verdict": "INCONCLUSIVE", "certifies_acceptance": False,
            "open_obligations": list(SAMPLING_OPEN_OBLIGATIONS)}


def sampling_errors(design, root, *, check_files=True):
    """Reject unsupported sampling claims even with perfectly consistent hashes.

    Removing these explicit blockers requires implementing and validating their
    evidence contracts. A new approval field cannot resolve an open obligation.
    """
    sampling = design.get("sampling", {})
    from validation.tier0_phase_contracts import SAMPLING, prospective_sampling_errors

    if sampling.get("selection_algorithm") == SAMPLING:
        return prospective_sampling_errors(design, root, check_files=check_files)
    errors = list(SAMPLING_OPEN_OBLIGATIONS)
    if sampling.get("selection_algorithm") != SELECTION_ALGORITHM:
        errors.append("Committed selection algorithm missing")
    documents = {}
    for name in ("exposure_ledger", "selection_manifest"):
        ref = sampling.get(name)
        if not isinstance(ref, dict) or not ref.get("path") or not _hex_digest(ref.get("sha256")):
            errors.append(f"Bound {name} missing")
        elif check_files:
            try:
                documents[name] = read_bound_json(root, ref)
            except (OSError, ValueError) as exc:
                errors.append(f"{name}: {exc}")
    if len(documents) == 2:
        try:
            report = replay_selection(documents["exposure_ledger"], documents["selection_manifest"])
            if report["entry_tasks"] != design.get("entry_tasks"):
                errors.append("Design tasks differ from recomputed selection")
            if set(design.get("tasks", {})) != set().union(*map(set, report["entry_tasks"].values())):
                errors.append("Design task catalog differs from selected task union")
        except ValueError as exc:
            errors.append(f"Selection replay: {exc}")
    return errors


def require_resource_authorization(design, phase, program, root):
    """Administrative spending permission only; never scientific validation."""
    from validation.tier0_design import resource_limits

    for evidence in program.get("evidence", []):
        if evidence.get("kind") != "tier0_resource_authorization" or phase not in evidence.get("phases", []):
            continue
        receipt = read_bound_json(root, {key: evidence.get(key) for key in ("path", "sha256")})
        if design.get("sampling", {}).get("selection_algorithm") == "prospective_named_suite_local_v1":
            expected_caps = {entry: resource_limits(design, entry)["campaign_cap_seconds"]
                             for entry in ("V04-T0", "V05")}
            if receipt.get("entry_caps_seconds") != expected_caps or receipt.get("run_schedule") != design.get("run_schedule"):
                continue
        if (receipt.get("kind") == "tier0_resource_authorization"
                and receipt.get("scope") == "resource_execution_only"
                and receipt.get("phase") == phase
                and receipt.get("design_digest") == _digest(design)
                and receipt.get("resource_digest") == _digest(design.get("resource"))
                and isinstance(receipt.get("authorization"), str) and receipt["authorization"].strip()):
            return
    raise ValueError("No hash-bound resource authorization for this exact design/phase; this is not a scientific verdict")
