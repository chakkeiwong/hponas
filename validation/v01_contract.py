"""Authorized finite V01 claim, exact corpus and source/dependency bindings."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sys

from tools.source_identity import ROOT, source_digest
from validation.tier0_design import canonical_digest
from validation.tier0_objectivity import read_bound_json
from validation.reference_checks import PASHA_REFERENCE, PASHA_SHA256, REFERENCE_FILES

SCOPE = "finite_reference_trace_conformance_v2"
CORPUS = "validation/designs/v01_finite_corpus_v2.json"
SEARCHERS = ("Random", "Sobol", "TPE", "CMA-ES", "GP", "LegacyGP")
SCHEDULERS = ("ASHA", "Median", "PASHA")
PACKAGES = ("numpy", "scipy", "torch", "botorch", "gpytorch", "optuna", "cmaes", "sortedcontainers")
REFERENCES = {
    "Random": "numpy.RandomState_uniform",
    "Sobol": "scipy.stats.qmc.Sobol_scrambled",
    "TPE": "optuna.samplers.TPESampler",
    "CMA-ES": "optuna.samplers.CmaEsSampler",
    "GP": "botorch_dim_scaled_matern52_qLogEI",
    "LegacyGP": "botorch_gamma_prior_matern52_seeded_qLogEI",
    "ASHA": "syne_tune_0_13_0_verbatim_promotion",
    "Median": "independent_completed_reference_running_mean",
    "PASHA": "syne_tune_0_13_0_sorted_set_pair_adapter",
}
RULE = {
    "pass": "all_required_trajectories_complete_and_frozen_missing_refusals_verified_with_exact_agreement",
    "fail": "any_reconstructed_observable_discrepancy",
    "inconclusive": "missing_execution_evidence_or_unexpected_incompleteness_without_observed_discrepancy",
    "priority": "fail_before_inconclusive_before_pass",
    "no_imputation_replacement_or_post_outcome_subsets": True,
    "distributional_equivalence": False,
    "scientific_performance_claim": False,
    "expected_missing_is_complete_trajectory": False,
    "complete_domain": "all_seed0_configurations_finite_at_every_original_fidelity_no_return_filter",
}


def binding(path, root=ROOT):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("V01 input escapes its source root")
    return {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _file(ref, root=ROOT):
    if (not isinstance(ref, dict) or set(ref) != {"path", "sha256"}
            or not isinstance(ref["path"], str) or Path(ref["path"]).is_absolute()):
        raise ValueError("Invalid V01 file binding")
    path = (Path(root).resolve() / ref["path"]).resolve()
    if binding(path, root) != ref:
        raise ValueError("Changed V01 input bytes")
    return path


def case_inventory(corpus):
    """Retain the complete Cartesian product, including incomplete tasks."""
    if (corpus.get("kind") != "v01_finite_corpus" or corpus.get("schema_version") != 2
            or corpus.get("scope") != SCOPE or corpus.get("components") != list(SEARCHERS + SCHEDULERS)
            or corpus.get("references") != REFERENCES or corpus.get("rule") != RULE):
        raise ValueError("Unknown finite V01 corpus/reference/rule")
    tables, seeds = corpus.get("tables", []), corpus.get("optimizer_seeds", [])
    if (not tables or len({row["id"] for row in tables}) != len(tables)
            or not seeds or len(set(seeds)) != len(seeds) or len(seeds) > 30
            or any(type(seed) is not int or not 0 <= seed < 2**31 for seed in seeds)):
        raise ValueError("Distinct tables and up to 30 fixed optimizer seeds required")
    counts = corpus.get("searcher_counts", {})
    if (set(counts) != set(SEARCHERS) or any(type(n) is not int or not 1 <= n <= 50 for n in counts.values())
            or type(corpus.get("scheduler_root_count")) is not int or not 1 <= corpus["scheduler_root_count"] <= 50):
        raise ValueError("Complete fixed component counts required")
    columns, resource = corpus.get("log_columns"), corpus.get("resource", {})
    limit = resource.get("maximum_elapsed_seconds")
    if (not isinstance(columns, list) or not all(isinstance(c, str) and c for c in columns)
            or len(columns) != len(set(columns)) or type(limit) not in (int, float)
            or not math.isfinite(limit) or not 0 < limit <= 600
            or type(resource.get("threads")) is not int or resource["threads"] != 1
            or resource.get("device") != "cpu"):
        raise ValueError("Explicit projection and bounded one-thread CPU recipe required")
    cases = []
    for table in tables:
        if (not isinstance(table.get("id"), str) or not table["id"] or "/" in table["id"]
                or type(table.get("table_seed")) is not int or table["table_seed"] < 0
                or table.get("role") not in {"original", "complete_domain"}):
            raise ValueError("Fixed recorded table seed required")
        missing = table.get("expected_missing", {})
        keys = {f"{seed}/{component}" for seed in seeds for component in SEARCHERS + SCHEDULERS}
        if (not isinstance(missing, dict) or not set(missing) <= keys
                or (missing and table["role"] != "original")):
            raise ValueError("Missing-cell exceptions must name frozen original cases")
        for cell in missing.values():
            if (not isinstance(cell, dict) or set(cell) != {"config_id", "seed", "training_steps", "status"}
                    or cell["status"] not in {"blank", "nonfinite"}
                    or any(type(cell[k]) is not int or cell[k] < 0 for k in ("config_id", "seed"))
                    or cell["seed"] != table["table_seed"]
                    or type(cell["training_steps"]) is not int or cell["training_steps"] <= 0):
                raise ValueError("Invalid frozen expected-missing source cell")
        for seed in seeds:
            for component in SEARCHERS + SCHEDULERS:
                cases.append({"id": f"{table['id']}/{seed}/{component}", "table": table["id"],
                    "optimizer_seed": seed, "table_seed": table["table_seed"], "component": component,
                    "count": counts[component] if component in SEARCHERS else corpus["scheduler_root_count"],
                    "fidelity": "maximum_recorded" if component in SEARCHERS else "all_recorded",
                    "reference": REFERENCES[component],
                    "expected_missing": missing.get(f"{seed}/{component}")})
    return cases


def prepare_contract():
    """Reconstruct exact accepted inputs before any case observes table values."""
    register = json.loads((ROOT / "validation/protocols.json").read_text())
    entry = register["entries"]["V01"]
    if (entry.get("scope_contract") != SCOPE or entry.get("decision_rule") != RULE
            or entry.get("corpus", {}).get("path") != CORPUS):
        raise ValueError("V01 protocol does not implement the accepted finite scope")
    corpus = read_bound_json(ROOT, entry["corpus"])
    approval = read_bound_json(ROOT, entry["scope_authorization"])
    if (approval.get("kind") != "v01_scope_authorization"
            or approval.get("decision") != "D-V01-COVERAGE-SCOPE"
            or approval.get("scientific_acceptance") is not False):
        raise ValueError("V01 scope authorization identity differs")
    _file(approval["proposal"])
    program = json.loads((ROOT / "docs/program/program.json").read_text())
    decision = next((d for d in program["decisions"] if d["id"] == "D-V01-COVERAGE-SCOPE"), {})
    if decision.get("status") != "accepted":
        raise ValueError("V01 scope amendment is not authorized")
    threads = {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")}
    if any(value != "1" for value in threads.values()):
        raise ValueError("Set OMP_NUM_THREADS=1 and OPENBLAS_NUM_THREADS=1 before V01 execution")
    cases = case_inventory(corpus)
    from validation.v01_data_coverage import verify_coverage_extension

    coverage = verify_coverage_extension(corpus, ROOT)
    for row in corpus["tables"]:
        _file(row["source"])
    for name, sha in REFERENCE_FILES.items():
        _file({"path": f"tests/fixtures/syne_tune_0_13_0/{name}", "sha256": sha})
    _file({"path": PASHA_REFERENCE, "sha256": PASHA_SHA256})
    return {"kind": "v01_frozen_finite_contract", "schema_version": 2, "scope": SCOPE,
            "source_digest": source_digest(), "python": platform.python_version(), "executable": sys.executable,
            "dependencies": {name: importlib.metadata.version(name) for name in PACKAGES},
            "protocol_register": binding(ROOT / "validation/protocols.json"),
            "individual_protocol": binding(ROOT / "validation/protocols/v01_protocol.md"),
            "protocol_entry_digest": canonical_digest(entry), "scope_authorization": entry["scope_authorization"],
            "corpus": entry["corpus"], "cases": cases, "rule": RULE, "coverage": coverage,
            "reference_sources": {**REFERENCE_FILES, "hyperband_pasha.py": PASHA_SHA256},
            "reference_adapter": binding(ROOT / "validation/reference_checks.py"),
            "trace_implementations": [binding(ROOT / name) for name in (
                "validation/v01_table_traces.py", "validation/v01_scheduler_traces.py", "validation/tabular_projection.py")],
            "numerical_execution": "cpu_float64_one_torch_thread", "thread_environment": threads,
            "trust": "instrumented_local_execution_no_hostile_host_authentication"}


def load_frozen(root, ref):
    frozen = read_bound_json(root, ref)
    if frozen != prepare_contract():
        raise ValueError("Frozen V01 contract differs from current source, dependencies or protocol")
    return frozen, read_bound_json(ROOT, frozen["corpus"])
