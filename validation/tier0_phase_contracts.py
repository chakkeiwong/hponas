"""Phase-scoped contracts; prospective local evidence is not historical secrecy.

These contracts disclose a conditional named-suite claim and a trusted local
recorder. They do not attest an unseen task population or external chronology.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sys

from validation.tier0_objectivity import read_bound_json

SAMPLING = "prospective_named_suite_local_v1"
ASSUMPTIONS = {
    "scope": "conditional_named_finite_suite",
    "exposure": "known_development_exposure_retained",
    "selection": "all_named_tasks_no_population_inference",
    "randomness": "independent_stationary_seed_vectors_conditional_on_fixed_experiment",
    "chronology": "trusted_local_write_once_freeze_before_execution",
    "isolation": "fresh_interpreter_bound_jobs_v1",
    "unseen_task_claim": False,
    "external_chronology_claim": False,
}
KL_SIZING_POLICY = {
    "method": "independent_pilot_bounded_kl_v1",
    "planning_error": .05,
    "confidence_components": 11,
    "count_rule": "smallest_sufficient_fixed_count_5_to_20",
    "pilot_use": "sizing_only_no_confirmation_reuse",
    "operational_bound": "binomial_tail_for_ten_percent_vector_loss_cap",
    "cost_scope": "conditional_on_frozen_resource_envelope_no_cost_veto",
}
JOINT_SIZING_POLICY = {
    "method": "independent_pilot_joint_event_v1",
    "planning_error": .05,
    "confidence_entries": 2,
    "good_vector_component_lower": [84, 125],
    "good_vector_requires": "all_components_at_threshold_and_no_unresolved_studies",
    "count_rule": "smallest_sufficient_fixed_count_5_to_20",
    "pilot_use": "sizing_only_no_confirmation_reuse",
    "operational_bound": "joint_good_vector_binomial_tail_covers_ten_percent_loss_cap",
    "cost_scope": "conditional_on_frozen_resource_envelope_no_cost_veto",
}
SIZING_POLICY = JOINT_SIZING_POLICY
PHASE_POLICY = {
    "development": "separate_capped_nonacceptance_recipe",
    "pilot": "exact_phase_freeze_and_prospective_rule_no_observed_effect_prerequisite",
    "confirmation": "reconstructed_independent_pilot_sizing_and_fresh_exact_phase_freeze",
    "scope_change": "explicit_authorization_not_scientific_evidence",
    "resources": "separate_exact_phase_authorization",
    "global_draft": "does_not_replace_concrete_phase_validation",
}

EXECUTION_VARIABLES = {"CUDA_VISIBLE_DEVICES", "JAX_PLATFORMS", "LD_LIBRARY_PATH",
                       "XLA_PYTHON_CLIENT_MEM_FRACTION"}


def execution_environment_errors(design, *, check_files=True):
    """Freeze the interpreter/device/loader settings that affect elapsed budgets."""
    if design.get("sampling", {}).get("selection_algorithm") != SAMPLING:
        return []
    contract = design.get("execution_environment", {})
    if not isinstance(contract, dict):
        return ["Frozen execution environment must be an object"]
    variables = contract.get("variables", {})
    if not isinstance(variables, dict):
        return ["Frozen execution variables must be an object"]
    errors = []
    if (contract.get("kind") != "single_gpu_runtime_v1"
            or not isinstance(contract.get("python"), str) or not Path(contract["python"]).is_absolute()
            or not isinstance(contract.get("device_kind"), str) or not contract["device_kind"]):
        errors.append("Frozen interpreter and single-GPU device contract required")
    if (set(variables) != EXECUTION_VARIABLES
            or any(not isinstance(value, str) or not value for value in variables.values())
            or variables.get("JAX_PLATFORMS") != "cuda"
            or not re.fullmatch(r"GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", variables.get("CUDA_VISIBLE_DEVICES", ""))):
        return errors + ["Frozen CUDA UUID and exact execution variables required"]
    try:
        fraction = float(variables.get("XLA_PYTHON_CLIENT_MEM_FRACTION", ""))
        if not 0 < fraction <= 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Explicit GPU memory fraction in (0,1] required")
    library_paths = variables.get("LD_LIBRARY_PATH", "").split(":")
    if any(not name or not Path(name).is_absolute() for name in library_paths):
        errors.append("Exact absolute CUDA library search paths required")
    if check_files and not errors:
        if not Path(contract["python"]).is_file() or any(not Path(name).is_dir() for name in library_paths):
            errors.append("Frozen interpreter or CUDA library directory is unavailable")
    return errors


def require_execution_environment(design, *, inspect_device=False):
    """Verify actual launch settings; worker checks its backend before PPO."""
    errors = execution_environment_errors(design)
    if errors:
        raise ValueError("; ".join(errors))
    if design.get("sampling", {}).get("selection_algorithm") != SAMPLING:
        return
    contract = design["execution_environment"]
    if sys.executable != contract["python"] or any(os.environ.get(key) != value
                                                  for key, value in contract["variables"].items()):
        raise ValueError("Actual execution environment differs from frozen experiment")
    if inspect_device:
        import jax

        devices = jax.devices()
        if (jax.default_backend() != "gpu" or len(devices) != 1
                or devices[0].device_kind != contract["device_kind"]):
            raise ValueError("Actual backend/device differs from frozen experiment")


def experiment_digest(design):
    """Only phase-level allocations/counts may change after the pilot."""
    from validation.tier0_design import canonical_digest

    ignored = {"version", "status", "notes", "selected_counts", "sizing_receipt", "phase_freeze",
               "resource", "planning_effects"}
    return canonical_digest({**{k: v for k, v in design.items() if k not in ignored},
                             "prespecified_pilot_counts": design.get("selected_counts", {}).get("pilot")})


def prospective_sampling_errors(design, root, *, check_files=True):
    from validation.tier0_design import canonical_digest

    sampling = design.get("sampling", {})
    errors = []
    if sampling.get("assumptions") != ASSUMPTIONS:
        errors.append("Prospective named-suite assumptions/scope differ")
    manifest = sampling.get("suite_manifest")
    if not isinstance(manifest, dict) or set(manifest) != {"path", "sha256"}:
        return errors + ["Bound prospective suite manifest missing"]
    if not check_files:
        return errors
    try:
        suite = read_bound_json(root, manifest)
        tasks = design.get("tasks", {})
        if (suite.get("kind") != SAMPLING or suite.get("entry_tasks") != design.get("entry_tasks")
                or suite.get("task_digest") != canonical_digest(tasks)
                or set(tasks) != set().union(*map(set, design.get("entry_tasks", {}).values()))):
            errors.append("Prospective suite/task coverage differs")
        if suite.get("known_exposure") != {task: "development_exposed" for task in tasks}:
            errors.append("Known development exposure must be retained for every task")
        # Exact historical documents support the disclosure, never non-exposure.
        refs = suite.get("exposure_records", [])
        if not refs:
            errors.append("Bound exposure records missing")
        for ref in refs:
            read_bound_json(root, ref)
        if suite.get("assumptions") != ASSUMPTIONS:
            errors.append("Suite manifest omits conditional claim/trust boundary")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"Prospective suite: {exc}")
    return errors


def verify_phase_freeze(design, phase, root):
    """Verify exact per-phase inputs; labels and broad program states are unused.

    A launch record is written before children run. The campaign's independent
    reconstruction checks the same record against the process chronology.
    """
    from validation.tier0_design import canonical_digest

    ref = design.get("phase_freeze")
    frozen = read_bound_json(root, ref)
    body = {k: v for k, v in design.items() if k != "phase_freeze"}
    if (frozen.get("kind") != "tier0_phase_freeze_v1" or frozen.get("phase") != phase
            or frozen.get("design_digest") != canonical_digest(body)
            or frozen.get("source_digest") != design.get("source_digest")
            or type(frozen.get("recorded_ns")) is not int or frozen["recorded_ns"] <= 0
            or not isinstance(frozen.get("boot_id"), str) or not frozen["boot_id"]):
        raise ValueError("Phase freeze differs from exact design/source/phase")
    if design.get("sizing_policy") != SIZING_POLICY:
        raise ValueError("Prospective independent pilot sizing rule missing")
    for scheduled_phase in ("pilot", "confirmation"):
        for entry in ("V04-T0", "V05"):
            campaign_directory(design, scheduled_phase, entry, root)
    protocols = frozen.get("protocols", {})
    if set(protocols) != {"V04-T0", "V05"}:
        raise ValueError("Both phase protocols must be frozen")
    for entry, binding in protocols.items():
        expected = f"validation/protocols/{entry.lower().replace('-', '_')}_protocol.md"
        if binding.get("path") != expected:
            raise ValueError("Wrong phase protocol identity")
        if hashlib.sha256((Path(root) / expected).read_bytes()).hexdigest() != binding.get("sha256"):
            raise ValueError("Changed phase protocol")
    return frozen


def campaign_directory(design, phase, entry, root):
    """One prespecified directory per entry/phase prevents choosing among reruns.

    The audited launcher creates it exclusively. Both phases' locations are
    part of experiment identity before pilot outcomes exist.
    """
    schedule = design.get("run_schedule", {})
    if set(schedule) != {"pilot", "confirmation"} or any(set(v) != {"V04-T0", "V05"} for v in schedule.values()):
        raise ValueError("Exact single-use pilot/confirmation run schedule missing")
    names = [name for entries in schedule.values() for name in entries.values()]
    if len(names) != len(set(names)):
        raise ValueError("Pilot and confirmation directories must be disjoint")
    for scheduled_phase, entries in schedule.items():
        for scheduled_entry, name in entries.items():
            if not isinstance(name, str):
                raise ValueError("Invalid scheduled campaign path")
            relative = Path(name)
            expected = Path("validation/artifacts") / scheduled_entry
            if (relative.is_absolute() or ".." in relative.parts or relative.parent != expected
                    or (Path(root) / relative).resolve().parent != (Path(root) / expected).resolve()):
                raise ValueError("Scheduled run must be a direct audited campaign directory")
    return (Path(root) / schedule[phase][entry]).resolve()


def require_prospective_scope(design, program, root):
    """A changed exposure/chronology scope requires recorded scope authorization.

    Authorization selects the claim to investigate; it cannot supply evidence.
    """
    for item in program.get("evidence", []):
        if item.get("kind") != "tier0_prospective_scope_authorization":
            continue
        receipt = read_bound_json(root, {key: item[key] for key in ("path", "sha256")})
        if (receipt.get("kind") == item["kind"] and receipt.get("assumptions") == ASSUMPTIONS
                and receipt.get("suite_manifest") == design["sampling"].get("suite_manifest")
                and isinstance(receipt.get("authorization"), str) and receipt["authorization"].strip()):
            return
    raise ValueError("Prospective named-suite exposure/chronology scope authorization missing")


def verify_phase_launch(launch, design, phase, search_freeze_ns, reports, root):
    """Local chronology only, independently compared with each child record."""
    from validation.tier0_design import canonical_digest

    frozen = verify_phase_freeze(design, phase, root)
    if (launch.get("kind") != "prospective_phase_launch_v1" or launch.get("phase") != phase
            or launch.get("design_digest") != canonical_digest(design)
            or launch.get("source_digest") != design.get("source_digest")
            or launch.get("phase_freeze") != design.get("phase_freeze")
            or type(launch.get("monotonic_ns")) is not int
            or not frozen["recorded_ns"] <= launch["monotonic_ns"] <= search_freeze_ns
            or launch.get("boot_id") != frozen["boot_id"]):
        raise ValueError("Prospective execution launch differs from frozen phase")
    for report in reports:
        if launch["monotonic_ns"] > report["launch_ns"] or launch["boot_id"] != report["observer"]["boot_id"]:
            raise ValueError("Prospective launch does not precede execution on the same boot")
