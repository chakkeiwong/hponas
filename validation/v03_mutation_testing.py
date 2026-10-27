#!/usr/bin/env python3
"""V03 inventory and decision using mutmut 3.8's complete result listing.

A cached inventory is diagnostic only. Use --run to execute a current campaign;
no cache is deleted and equivalent exclusions require an individual proof.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ET

from validation.v03_raw_outcomes import RAW_OUTCOME_POLICY, reconstruct_raw_outcomes
from tools.source_identity import dependency_versions
from validation.v03_resource_scheduler import POLICY_PATH, policy as resource_policy

TARGET_KILL_SCORE = 0.90
EQUIVALENT_MUTANT_ALLOWANCE = 0.05
MIN_MUTANTS = 100
MAX_TIMEOUT_RATE = 0.20
MAX_CAMPAIGN_WALL_SECONDS = 10 * 60 * 60
MUTANT_TIMEOUT_CONSTANT = 22.0
MUTANT_TIMEOUT_MULTIPLIER = 3.0
CALIBRATION_WALL_SECONDS = 2700
MAX_MUTATION_WORKERS = 24

# Exact reviewed v6 overlay; ordered names and bytes are part of the phase.
REQUIRED_TOOL_SOURCES = [
    {
        "relative_path": "__init__.py",
        "sha256": "e907533ddfa85ae95a5669993fe759bc08ef00a21658336202202d1e1cb61d6d"
    },
    {
        "relative_path": "__main__.py",
        "sha256": "f32efe3ef83379b013725d04f2b1d738c83d940abb8470d1e56193e9da56fc55"
    },
    {
        "relative_path": "code_coverage.py",
        "sha256": "b0d7dc9a8841dfa54e49fe5002ddb568cd7cc62b16f548554dcf52577013d970"
    },
    {
        "relative_path": "configuration.py",
        "sha256": "c9933b8da52e69604daf509ffb6f08904bdca408aefce3cfc3568c01ff6f1af7"
    },
    {
        "relative_path": "core.py",
        "sha256": "7fcc8eb26fe0e798efab4c0e03fbe3f93f5e034d3e329fa525645b7afdb6e7a7"
    },
    {
        "relative_path": "hponas_evidence.py",
        "sha256": "955d8c3dc9b83d9eb7de3770d99d8af71bc3bbda28c8675798253ea854441a94"
    },
    {
        "relative_path": "hponas_scheduler.py",
        "sha256": "0fd3d757edbd17b5581ae8280b5e2bffd8a341d55005df41f5803200b9b387d5"
    },
    {
        "relative_path": "models/__init__.py",
        "sha256": "fe1a8196124b4bb56ab9fc913febf3259a2b44cfce469ad4307a8e3ee8e03588"
    },
    {
        "relative_path": "models/results.py",
        "sha256": "d2702c2cfd3d46024c692e601fecbab61cb66abda15c36ebd78d74f46fe02583"
    },
    {
        "relative_path": "mutation/__init__.py",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
        "relative_path": "mutation/data.py",
        "sha256": "de6e43ecb99ac4c2197410e89dc25cbb50952d7e9e1c4216cd9e6c1e8209a6f2"
    },
    {
        "relative_path": "mutation/diff_apply.py",
        "sha256": "3dfa739a362138e885444360157cc1ef608a20b84e6eb4325a2e83f283002e39"
    },
    {
        "relative_path": "mutation/file_mutation.py",
        "sha256": "a8cf64d1a1442ed1dbdbaeb59e7893dc902dbba8c1f723ead133a237b4335364"
    },
    {
        "relative_path": "mutation/mutators.py",
        "sha256": "197eae529cde0d1f0e5dc30cb41224a2f5b92454b03f2d69777785b007a1833f"
    },
    {
        "relative_path": "mutation/pragma_handling.py",
        "sha256": "f18c5e3e9a829f54e5aaa51cdaf44317ab61640a405b6918b772f362675b89a5"
    },
    {
        "relative_path": "mutation/trampoline.py",
        "sha256": "95162d6315056960f3551ba4b532bb34deb30fec7668c61be1f7a93bb1bb42d1"
    },
    {
        "relative_path": "mutation/trampoline_templates.py",
        "sha256": "836cdd8cc881482e2ecd6f1f4fb03e8c7823a9f72b181789772f36e6e4fe3782"
    },
    {
        "relative_path": "runners/__init__.py",
        "sha256": "7985fd4e0b7abd2c5d24db79d44ca7892bf5486e3af29669cb1b3c17cd88b322"
    },
    {
        "relative_path": "runners/harness.py",
        "sha256": "667da68b2a6f7f7bccabb0fcace8392288008194df78119a7c690601104da9d1"
    },
    {
        "relative_path": "state.py",
        "sha256": "322d20e19411d34dc90744325ba9a3ef27f946dfaca89dd59a8471092b86e875"
    },
    {
        "relative_path": "stats.py",
        "sha256": "b499ec9e6e4d0bd792898b8979744b5108498201ee68f6eb7e137c498dae4bd5"
    },
    {
        "relative_path": "type_checking.py",
        "sha256": "833708742c87b61c3e2a211ffc467281c57c42fcb9315a4a8cdfcb047d95f06d"
    },
    {
        "relative_path": "ui/__init__.py",
        "sha256": "94141bfffc56085fb1a1a535cb7f9e90caaad57d76cc8aaa799d4cbdc5122f36"
    },
    {
        "relative_path": "ui/browse.py",
        "sha256": "09a34226d4093ee6856d4ecef302ba328208361e45c79fc361969e34319d7aac"
    },
    {
        "relative_path": "ui/terminal.py",
        "sha256": "03c31ef7800e806bc5900a7ea9d722a4756f848fb60fe67f9f4b9e5610661005"
    },
    {
        "relative_path": "utils/__init__.py",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
        "relative_path": "utils/file_utils.py",
        "sha256": "1757d79ac9d53163916eeef725c6e8fe3683447ecd818792366677a415077c63"
    },
    {
        "relative_path": "utils/format_utils.py",
        "sha256": "d88a4362a4ed21606cb74d7417654f18b44155f132c084c9774e3de93209c00e"
    },
    {
        "relative_path": "utils/logging_utils.py",
        "sha256": "de6081569bbf0882714a1cf648898e7c6e2c88ff5548784076b2c5028fca8420"
    },
    {
        "relative_path": "utils/safe_setproctitle.py",
        "sha256": "a266ee10efdd5639347a19f18f60e88956dfd9c292e65eae5d06552c9e0556a5"
    },
    {
        "relative_path": "workers/__init__.py",
        "sha256": "e2c55429239e3ec0ee46c482c6d36521b8b8a74fda30970b73d4c1bcbbd09ae8"
    },
    {
        "relative_path": "workers/coordinator_cleanup.py",
        "sha256": "963e37668f45a15fa75abf3c2b50831d31ee732ed83804586e5ab4789cfd6025"
    },
    {
        "relative_path": "workers/descendant_supervisor.py",
        "sha256": "bc4d28a7528c0492163f4ec27e14d812236ed0088f9d3c3f9102af636310d0f3"
    },
    {
        "relative_path": "workers/isolation.py",
        "sha256": "5365fef8ebcc4a9bf0f79bbffc8290072d3009c99d94d6bf29600531b548ad93"
    },
    {
        "relative_path": "workers/timeout.py",
        "sha256": "ff5027bdae778385ce4cecc6c883ee1fde78c8a7d403a4af318145451700527c"
    }
]
EXECUTION_ADMISSION = {'kind': 'guarded_single_full_allocation_v1', 'complete_timing_census_required': False, 'prerequisites': ['descendant_cleanup_controls', 'exact_leaking_mutant_selected_tests', 'independent_resource_guard_controls', 'current_complete_calibration', 'python312_python313_installation', 'local_operation_change_impact', 'protocol_refusal_controls', 'six_program_checks'], 'official_runs_per_allocation': 1, 'automatic_retry': False, 'prior_scientific_outcomes_reused': False, 'incomplete_or_resource_intervention': 'INCONCLUSIVE_REPAIR_REQUIRED'}
CALIBRATION_FUNCTION = "hponas.searchers_gp.xǁGPqLogEISearcherǁ_build_acqf"
CALIBRATION_CONTROLS = {
    CALIBRATION_FUNCTION + "__mutmut_2": {
        "status": "survived", "removed": "    X_train = torch.stack(self._X)",
        "added": "    X_train = None",
    },
    CALIBRATION_FUNCTION + "__mutmut_3": {
        "status": "killed", "removed": "    X_train = torch.stack(self._X)",
        "added": "    X_train = torch.stack(None)",
    },
}
CALIBRATION_ORDER_TESTS = (
    "tests/integration/test_ray_streaming.py::test_ray_study_continuation_and_replay[restart-6]",
    "tests/integration/test_ray_streaming.py::test_ray_streaming_timeout_cancels_worker_and_retains_progress",
    "tests/integration/test_ray_streaming.py::test_ray_worker_crash_retries_without_double_counting_reports",
    "tests/integration/test_ray_cluster_ownership.py::test_study_owns_cluster_across_streamed_batches_and_can_restart_it",
)
IN_SCOPE_MODULES = [
    "hponas.searchers.base",
    "hponas.searchers.gp_searcher",
    "hponas.searchers.random_searcher",
    "hponas.executors.local_executor",
    "hponas.executors.ray_executor",
    "hponas.legacy_searchers",
    "hponas.searchers_tpe",
    "hponas.searchers_gp",
    "hponas.architecture",
    "hponas.priors",
    "hponas.legacy_executors",
    "hponas.schedulers",
    "hponas.space",
    "hponas.types",
    "hponas.study",
    "hponas.replay",
    "hponas.events",
    "hponas.encoding",
    "hponas.persistence",
    "hponas.executors.base",
    "hponas.executors.reporting",
    "hponas.searchers.adapter",
    "hponas.searchers.cmaes_searcher",
    "hponas.store",
]
DEFERRED_MODULES = {
    # PAR-01 has separate finite/resource/hardware conformance evidence.
    # These owners do not claim Tier-0 mutation coverage or narrow its scope.
    "hponas.adapter_parallel": "PAR-01",
    "hponas.evaluation_parallel": "PAR-01",
    "hponas.executors.leases": "PAR-01",
    "hponas.executors.ray_resources": "PAR-01",
    "hponas.executors.resource_executor": "PAR-01",
    "hponas.executors.resources": "PAR-01",
    "hponas.executors.worker_bootstrap": "PAR-01",
    "hponas.parallel": "PAR-01",
    "hponas.parallel_transfer": "PAR-01",
    "hponas.population_parallel": "PAR-01",
    # Restored product contracts use finite behavioral qualification; BANK-01
    # owns their final-source integration. This is not mutation coverage.
    "hponas.evaluation": "PRD-01",
    "hponas.evaluation_streaming": "GAP-01",
    "hponas.population_adapter": "GAP-01",
    "hponas.local_service": "GAP-01",
    "hponas.backup_security": "GAP-01",
    "hponas.rgpe": "GAP-01",
    "hponas.quickstart": "GAP-01",
    "hponas.budgets": "PRD-01",
    "hponas.capabilities": "PRD-01",
    "hponas.diagnostics": "PRD-01",
    "hponas.reporting": "PRD-01",
    "hponas.searchers_cost": "T1-COST",
    "hponas.searchers_mo": "T1-MO",
    "hponas.reporting_mo": "T1-MO",
    "hponas.searchers_priorband": "PRI-01",
    "hponas.warm_start": "T1-WARM",
    # Outside the Tier-0 mutation population, with separate finite/engineering
    # obligations. Completion of those obligations is not mutation coverage.
    "hponas.bg_pbt": "T2-POP",
    "hponas.bg_population": "T2-POP",
    "hponas.categorical_prior": "PRI-01",
    "hponas.cost_inference": "T1-COST",
    "hponas.cost_likelihood": "T1-COST",
    "hponas.cost_policy": "T1-COST",
    "hponas.cost_searcher": "T1-COST",
    "hponas.dehb": "T3-01",
    "hponas.generational_transfer": "T2-POP",
    "hponas.gp_robustness": "T3-01",
    "hponas.multi_objective": "T1-MO",
    "hponas.operations": "OPS-01",
    "hponas.pb2_mix": "T2-POP",
    "hponas.population": "T2-POP",
    "hponas.population_bandit": "T2-POP",
    "hponas.population_gp": "T2-POP",
    "hponas.population_search": "T2-POP",
    "hponas.postgres": "OPS-01",
    "hponas.postgres_operations": "OPS-01",
    "hponas.prior_band": "PRI-01",
    "hponas.prior_sampling": "PRI-01",
    "hponas.product_prior": "PRI-01",
    "hponas.schedulers_mo": "T1-MO",
    "hponas.schedulers_prior": "PRI-01",
    "hponas.searchers.multi_objective": "T1-MO",
    "hponas.searchers.prior": "PRI-01",
    "hponas.searchers.priorband": "PRI-01",
    "hponas.searchers.product_priorband": "PRI-01",
    "hponas.searchers.robust_gp_searcher": "T3-01",
    "hponas.study_mo": "T1-MO",
    "hponas.trust_controller": "T1-TRUST",
    "hponas.trust_searcher": "T1-TRUST",
    "hponas.trust_space": "T1-TRUST",
    "hponas.warm_history": "T1-WARM",
}
FACADE_MODULES = {"hponas.__init__", "hponas.executors.__init__", "hponas.searchers.__init__"}
PARALLEL_TEST_BOUNDARIES = (
    'tests/integration/test_resource_executor.py',
    'tests/integration/test_parallel_study.py',
    'tests/integration/test_parallel_population.py',
    'tests/integration/test_parallel_methods.py',
    'tests/integration/test_parallel_hardware.py',
    'tests/integration/test_parallel_ray.py',
    'tests/unit/test_parallel_resources.py',
    'tests/unit/test_parallel_program_boundary.py',
)
MUTATION_TEST_ARGUMENTS = (
    '-p', 'tools.v03_test_order', '--ignore=tests/scale',
    '--ignore=tests/unit/test_ray_executor_tier0.py',
    '--ignore=tests/test_ray_executor.py', '-m', 'not slow', '--tb=short', '-q',
    *('--ignore=' + path for path in PARALLEL_TEST_BOUNDARIES),
)


def verify_test_selection(config):
    """Keep inherited tests and explicitly separate new PAR-01 resources."""
    if config.get('pytest_add_cli_args') != list(MUTATION_TEST_ARGUMENTS):
        raise ValueError('V03 test selection differs from the reviewed resource boundary')


CRITICAL_PATHS = (
    "evaluate_trial",
    "GPSearcherǁsuggest",
    "GPSearcherǁ_suggest_impl",
    "GPSearcherǁ_suggest_joint_impl",
    "GPSearcherǁ_joint_finite",
    "GPSearcherǁsuggest_batch",
    "GPSearcherǁpending_locations",
    "GPSearcherǁ_prepare_training_data",
    "ASHASchedulerǁpromote",
    "ASHASchedulerǁreport",
    "ASHASchedulerǁ_median_should_stop",
    "ASHASchedulerǁfinish",
    "_promotion_cutoff",
    "_ceil_population_ratio",
    "TrialReporterǁ__call__",
    "BudgetedASHASchedulerǁpromote",
    "PASHASchedulerǁ_maybe_increase_resources",
    "PASHASchedulerǁ_update_epsilon",
    "PASHASchedulerǁpromote",
    "PASHASchedulerǁreport",
    "PASHASchedulerǁload_state_dict",
    "CMAESSearcherǁsuggest",
    "CMAESSearcherǁobserve",
    "CMAESSearcherǁset_state",
    "TPESearcherǁpropose",
    "TPESearcherǁobserve",
    "TPESearcherǁload_state_dict",
    "GPqLogEISearcherǁ_build_gp",
    "GPqLogEISearcherǁ_build_acqf",
    "GPqLogEISearcherǁpropose",
    "GPqLogEISearcherǁ_propose",
    "GPqLogEISearcherǁobserve",
    "GPqLogEISearcherǁload_state_dict",
    "CoordinateMLPǁ__init__",
    "build",
    "compatible",
    "transfer_policy",
    "MOASHASchedulerǁpromote",
    "LocalExecutorǁ_execute_impl",
    "LocalExecutorǁ_execute_streaming_process",
    "LocalExecutorǁlaunch",
    "RayExecutorǁ_collect_with_retry",
    "RayExecutorǁ_execute_streaming",
    "RayExecutorǁ_cancel_and_drain",
    "Studyǁrun",
    "Studyǁload_checkpoint",
    "Studyǁ_on_progress",
    "Studyǁ_accept",
    "ReplayEngineǁverify_determinism",
)
STATUSES = {
    "killed",
    "survived",
    "timeout",
    "no tests",
    "suspicious",
    "not checked",
    "segfault",
    "check was interrupted by user",
    "skipped",
    "caught by type check",
}
UNRESOLVED_STATUSES = {"not checked", "suspicious", "segfault", "check was interrupted by user",
                       "skipped", "caught by type check"}


def parse_listing(output: str) -> dict:
    mutants = []
    seen = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        name, sep, status = line.strip().rpartition(": ")
        if not sep or status not in STATUSES or "__mutmut_" not in name:
            raise ValueError(f"Unrecognized mutmut result: {line!r}")
        if name in seen:
            raise ValueError(f"Duplicate mutant: {name}")
        seen.add(name)
        module = name.split(".x", 1)[0]
        mutants.append({"id": name, "module": module, "status": status})
    counts = Counter(m["status"] for m in mutants)
    return {
        "total_mutants": len(mutants),
        **{k.replace(" ", "_"): counts[k] for k in STATUSES},
        "mutants": mutants,
    }


def parse_mutmut_results(cwd=None) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "mutmut", "results", "--all", "true"],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )
    return parse_listing(result.stdout)


def raw_metadata_bindings(workspace):
    """Bind every required module's actual process outcomes after workers stop."""
    return [{"module": module,
             "binding": _binding(Path(workspace) / "mutants" / (module.replace(".", "/") + ".py.meta"))}
            for module in IN_SCOPE_MODULES
            if (Path(workspace) / "mutants" / (module.replace(".", "/") + ".py.meta")).is_file()]


def reconstruct_inventory(listing, metadata):
    listed = parse_listing(listing)
    present = {row["module"] for row in metadata}
    if present - set(IN_SCOPE_MODULES):
        raise ValueError("Unexpected raw mutation module")
    rows = reconstruct_raw_outcomes(listed["mutants"], metadata, present)
    counts = Counter(row["status"] for row in rows)
    return {"total_mutants": len(rows), "mutants": rows,
            "missing_raw_modules": sorted(set(IN_SCOPE_MODULES) - present),
            **{status.replace(" ", "_"): counts[status] for status in STATUSES}}


def reconstruct_observation(listing, metadata, listing_returncode):
    """Retain a failed collection as unresolved evidence, never an empty PASS."""
    for entry in metadata:
        _read_bound(entry["binding"], parse=False)
    if type(listing_returncode) is not int:
        raise ValueError("Missing result-listing process exit code")
    try:
        if listing_returncode != 0:
            raise ValueError(f"Result-listing process exited {listing_returncode}")
        return dict(reconstruct_inventory(listing, metadata), inventory_error=None)
    except ValueError as exc:
        return {"total_mutants": 0, "mutants": [], "inventory_error": str(exc),
                "missing_raw_modules": sorted(set(IN_SCOPE_MODULES) - {row["module"] for row in metadata}),
                **{status.replace(" ", "_"): 0 for status in STATUSES}}


def analyze_results(
    results: dict, equivalents: list | None = None, required_modules=None
) -> dict:
    """Compute all protocol vetoes from individual records, never reported totals."""
    mutants = results.get("mutants", [])
    if not mutants:
        return {
            "passed": False,
            "kill_score": 0.0,
            "denominator": 0,
            "timeout_rate": 0.0,
            "per_module": [],
            "critical_survivors": [],
            "errors": ["No individual mutant records"],
            "equivalent_mutants": 0,
        }
    ids = {m["id"]: m for m in mutants}
    if len(ids) != len(mutants):
        raise ValueError("Duplicate mutant records")
    from validation.v03_equivalence import verify_certificate
    from validation.evidence import ROOT

    exclusions = set()
    for entry in equivalents or []:
        mid = entry.get("id")
        if (
            mid not in ids
            or mid in exclusions
            or ids[mid]["status"] != "survived"
            or not entry.get("rule")
        ):
            raise ValueError(
                "Each equivalent must identify a unique survivor with a checkable proof"
            )
        verify_certificate(entry, ROOT)
        exclusions.add(mid)
    grouped = defaultdict(list)
    for mutant in mutants:
        if (
            mutant["module"] != mutant["id"].split(".x", 1)[0]
            or "__mutmut_" not in mutant["id"]
        ):
            raise ValueError("Mutant identity/module mismatch")
        if mutant["status"] not in STATUSES:
            raise ValueError(f"Unknown status: {mutant['status']}")
        grouped[mutant["module"]].append(mutant)

    def score(items):
        counts = Counter(m["status"] for m in items)
        eq = sum(m["id"] in exclusions for m in items)
        denom = len(items) - counts["timeout"] - eq
        return {
            "total_mutants": len(items),
            "killed": counts["killed"],
            "survived": counts["survived"],
            "timeout": counts["timeout"],
            "no_tests": counts["no tests"],
            "equivalent": eq,
            "denominator": denom,
            "kill_score": counts["killed"] / denom if denom else 0.0,
        }

    overall = score(mutants)
    modules = [
        {"module": module, **score(items)} for module, items in sorted(grouped.items())
    ]
    critical = [
        m["id"]
        for m in mutants
        if m["status"] == "survived"
        and m["id"] not in exclusions
        and m["id"]
        .rsplit(".", 1)[-1]
        .split("__mutmut_", 1)[0]
        .removeprefix("xǁ")
        .removeprefix("x_")
        in CRITICAL_PATHS
    ]
    required = set(IN_SCOPE_MODULES if required_modules is None else required_modules)
    errors = []
    if required - set(grouped):
        errors.append("Missing modules: " + ", ".join(sorted(required - set(grouped))))
    if len(mutants) < MIN_MUTANTS:
        errors.append("Fewer than 100 mutants")
    if overall["kill_score"] < TARGET_KILL_SCORE:
        errors.append("Overall kill score below 0.90")
    if any(m["kill_score"] < TARGET_KILL_SCORE for m in modules):
        errors.append("Module kill score below 0.90")
    if critical:
        errors.append("Unproved critical-path survivors")
    if len(exclusions) > len(mutants) * EQUIVALENT_MUTANT_ALLOWANCE:
        errors.append("Equivalent allowance exceeds 5%")
    if any(m["status"] in UNRESOLVED_STATUSES for m in mutants):
        errors.append("Incomplete or abnormal mutant outcomes")
    timeout_rate = overall["timeout"] / len(mutants)
    if timeout_rate > MAX_TIMEOUT_RATE:
        errors.append("Timeout rate exceeds 20%")
    return {
        **overall,
        "passed": not errors,
        "timeout_rate": timeout_rate,
        "per_module": modules,
        "critical_survivors": critical,
        "equivalent_mutants": len(exclusions),
        "errors": errors,
    }


def _run_with_deadline(command, cwd, env, timeout, stdout=None):
    """Bound wall time as mutmut's CPU limits cannot bound blocked workers."""
    with subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True,
                          stdout=stdout, stderr=subprocess.STDOUT if stdout is not None else None) as process:
        try:
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Allow mutmut to save its partial inventory and stop its workers.
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                return False
            if returncode:
                raise subprocess.CalledProcessError(returncode, command)
        finally:
            # The coordinator may crash while its workers/native services live.
            # Its isolated process group remains ours even after the leader exits.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            else:
                time.sleep(1)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    return True


def inventory_verdict(results, analysis):
    """Interrupted/abnormal evidence cannot be mistaken for a regular FAIL."""
    if (results.get("inventory_error") or results.get("missing_raw_modules") or analysis.get("timeout_rate", 0) > MAX_TIMEOUT_RATE
            or any(row["status"] in UNRESOLVED_STATUSES
                   for row in results.get("mutants", []))):
        return "INCONCLUSIVE"
    return "PASS" if analysis["passed"] else "FAIL"


def _binding(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_data_inventory(root):
    """Bind test data and explicitly selected document and support inputs."""
    from tools.source_identity import test_data_paths

    root = Path(root).resolve()
    paths = set(test_data_paths(root))
    config_path = root / "pyproject.toml"
    if config_path.is_file():
        config = tomllib.loads(config_path.read_text()).get("tool", {}).get("mutmut", {})
        for name in config.get("also_copy", []):
            if not name.startswith(("docs/", "program_operations/")):
                continue
            selected = root / name
            if not selected.exists() or not selected.resolve().is_relative_to(root):
                raise ValueError("Missing or external mutation document input")
            paths.update(path for path in (selected.rglob("*") if selected.is_dir() else [selected])
                         if path.is_file() and "__pycache__" not in path.parts)
    if any(not path.resolve().is_relative_to(root) for path in paths):
        raise ValueError("Mutation document inputs must reside in the frozen workspace")
    return [{"relative_path": str(path.relative_to(root)), "binding": _binding(path)} for path in sorted(paths)]


def same_test_data(expected, observed):
    def identities(rows):
        result = []
        for row in rows:
            _read_bound(row["binding"], parse=False)
            result.append((row["relative_path"], row["binding"]["sha256"]))
        if len(result) != len({path for path, _ in result}):
            raise ValueError("Duplicate frozen test-data identity")
        return sorted(result)

    return identities(expected) == identities(observed)


def _write_once(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def library_ownership(workspace):
    """Account for every library file independently of the mutmut path list."""
    required = set(IN_SCOPE_MODULES)
    if (len(required) != len(IN_SCOPE_MODULES) or required & set(DEFERRED_MODULES)
            or (required | set(DEFERRED_MODULES)) & FACADE_MODULES):
        raise ValueError("Overlapping or duplicate V03 module ownership")
    files = {str(p.relative_to(workspace).with_suffix("")).replace("/", "."): p
             for p in sorted((workspace / "hponas").rglob("*.py"))}
    declared = required | set(DEFERRED_MODULES) | FACADE_MODULES
    if set(files) != declared:
        raise ValueError(f"Unassigned or missing library modules: {sorted(set(files) ^ declared)}")
    rows = []
    for module, path in files.items():
        source = path.read_text()
        if module in FACADE_MODULES and any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                                           for n in ast.walk(ast.parse(source))):
            raise ValueError(f"Executable implementation added to an import facade: {module}")
        if module in required and "pragma: no mutate" in source:
            raise ValueError(f"Hidden mutation exclusion in required module: {module}")
        rows.append({"module": module, "source_path": str(path.relative_to(workspace)),
                     "sha256": _binding(path)["sha256"],
                     "disposition": "required" if module in required else
                     "deferred" if module in DEFERRED_MODULES else "import_facade",
                     "work_item": DEFERRED_MODULES.get(module, "V03-03")})
    return rows


def verify_frozen_tool_sources(sources, manifest):
    """Reconstruct the exact reviewed ordered inventory, including retained copies."""
    if (manifest != REQUIRED_TOOL_SOURCES or len(sources) != len(REQUIRED_TOOL_SOURCES)
            or len({row["path"] for row in sources}) != len(sources)):
        raise ValueError("V03 tool source inventory differs from the reviewed overlay")
    for source, expected in zip(sources, REQUIRED_TOOL_SOURCES):
        _read_bound(source, parse=False)
        if source["sha256"] != expected["sha256"]:
            raise ValueError("V03 tool source bytes differ from the reviewed overlay")


def verify_tool_overlay(tool_root):
    """Refuse renamed, stale, missing, extra or altered runtime tool files."""
    tool_root = Path(tool_root).resolve()
    if tool_root.name != "mutmut" or tool_root.parent.name != "mutmut-evidence-v6":
        raise ValueError("V03 requires the reviewed pidfd-owned mutmut overlay")
    paths = sorted(tool_root.rglob("*.py"))
    if any(not path.resolve().is_relative_to(tool_root) for path in paths):
        raise ValueError("V03 tool source escapes the reviewed overlay")
    sources = [_binding(path) for path in paths]
    manifest = [{"relative_path": str(path.relative_to(tool_root)), "sha256": ref["sha256"]}
                for path, ref in zip(paths, sources)]
    verify_frozen_tool_sources(sources, manifest)
    return sources, manifest


def mutation_freeze(workspace):
    """Freeze the actual tool, test selection and complete population contract."""
    import mutmut
    from validation.evidence import source_digest
    from validation.v03_equivalence import RULES, verify_proof_source_contexts

    version = importlib.metadata.version("mutmut")
    if version != "3.8.0":
        raise ValueError("V03 requires the pinned mutmut 3.8.0")
    verify_phase_register(workspace)
    ownership = library_ownership(workspace)
    config = tomllib.loads((workspace / "pyproject.toml").read_text())["tool"]["mutmut"]
    if (config.get("process_isolation"), config.get("forkserver_warmup"),
            config.get("max_forkserver_restarts")) != ("forkserver", "none", 0):
        raise ValueError("V03 requires explicit clean forkserver isolation without hidden retries")
    if (config.get("timeout_constant"), config.get("timeout_multiplier")) != (
            MUTANT_TIMEOUT_CONSTANT, MUTANT_TIMEOUT_MULTIPLIER):
        raise ValueError("V03 requires the calibrated selected-test startup allowance")
    arguments = config.get("pytest_add_cli_args", [])
    if sum(arguments[index:index + 2] == ["-p", "tools.v03_test_order"]
           for index in range(len(arguments))) != 1:
        raise ValueError("V03 requires the inventory-preserving deterministic test order")
    verify_test_selection(config)
    if (config.get("only_mutate") or config.get("do_not_mutate") or config.get("do_not_mutate_patterns")
            or config.get("type_check_command") or config.get("mutate_only_covered_lines", False)):
        raise ValueError("V03 forbids narrowing the complete configured population")
    configured = set()
    for name in config["source_paths"]:
        path = workspace / name
        paths = path.rglob("*.py") if path.is_dir() else [path]
        configured.update(str(p.relative_to(workspace).with_suffix("")).replace("/", ".")
                          for p in paths if p.name != "__init__.py")
    if configured != set(IN_SCOPE_MODULES):
        raise ValueError("V03 configured source paths differ from the required modules")
    verify_proof_source_contexts(workspace)
    tool_root = Path(mutmut.__file__).resolve().parent
    tool_sources, tool_manifest = verify_tool_overlay(tool_root)
    return {"kind": "v03_execution_freeze_v8", "source_digest": source_digest(workspace),
            "recorded_ns": time.monotonic_ns(), "tool_version": version, "python": sys.executable,
            "tool_sources": tool_sources, "tool_source_manifest": tool_manifest,
            "dependencies": dependency_versions(),
            "config": config, "config_file": _binding(workspace / "pyproject.toml"),
            "protocol": _binding(workspace / "validation/protocols/v03_protocol.md"),
            "protocol_register": _binding(workspace / "validation/protocols.json"),
            "required_modules": IN_SCOPE_MODULES, "critical_paths": list(CRITICAL_PATHS),
            "library_ownership": ownership,
            "test_data_inputs": test_data_inventory(workspace),
            "calibration_controls": CALIBRATION_CONTROLS,
            "calibration_order_tests": list(CALIBRATION_ORDER_TESTS),
            "calibration_wall_seconds": CALIBRATION_WALL_SECONDS,
            "equivalence_rules": list(RULES),
            "equivalence_argument": _binding(workspace / "docs/program/MUTATION_EQUIVALENCE_LEMMAS_2026_10_23.md"),
            "raw_outcome_policy": RAW_OUTCOME_POLICY,
            "resource_policy": _binding(workspace / "validation/designs/v03_resource_policy.json"),
            "max_workers": MAX_MUTATION_WORKERS, "wall_seconds": MAX_CAMPAIGN_WALL_SECONDS}


def verify_phase_register(workspace):
    """Refuse launching a prospective checker against an older phase contract."""
    from validation.v03_equivalence import RULES

    workspace = Path(workspace)
    entry = json.loads((workspace / "validation/protocols.json").read_text())["entries"]["V03"]
    decision = entry["decision_rule"]
    expected = {"overall_minimum": TARGET_KILL_SCORE, "every_module_minimum": TARGET_KILL_SCORE,
                "critical_survivors": 0, "equivalent_maximum_fraction": EQUIVALENT_MUTANT_ALLOWANCE,
                "minimum_mutants": MIN_MUTANTS, "timeout_maximum_fraction": MAX_TIMEOUT_RATE,
                "abnormal_or_unchecked": "INCONCLUSIVE", "equivalence_rules": list(RULES),
                "raw_outcome_policy": RAW_OUTCOME_POLICY, "raw_kill_exit_code": 1, "raw_timeout_exit_code": -24}
    if (entry.get("version") != "2.31" or any(decision.get(key) != value for key, value in expected.items())
            or entry.get("tool_source_manifest") != REQUIRED_TOOL_SOURCES
            or entry.get("execution_admission") != EXECUTION_ADMISSION
            or entry.get("test_selection") != list(MUTATION_TEST_ARGUMENTS)
            or entry.get("execution_resources") != {"workers": MAX_MUTATION_WORKERS,
                "cpu_slots": "distinct_inherited_cpu_per_live_child",
                "wall_seconds": MAX_CAMPAIGN_WALL_SECONDS,
                "calibration_wall_seconds": CALIBRATION_WALL_SECONDS,
                "scheduler": resource_policy()}
            or entry.get("module_ownership") != {
                "required": IN_SCOPE_MODULES, "outside_scope": DEFERRED_MODULES,
                "import_facades": sorted(FACADE_MODULES)}
            or "**Version:** 2.31" not in (workspace / "validation/protocols/v03_protocol.md").read_text()):
        raise ValueError("V03 phase register differs from the prospective executable contract")


def _read_bound(binding, parse=True):
    path = Path(binding["path"])
    if not path.is_absolute() or _binding(path) != binding:
        raise ValueError("Changed or missing V03 execution artifact")
    return json.loads(path.read_text()) if parse else path.read_text()


def verify_calibration(record, frozen):
    """Reconstruct the diagnostic from raw controls, not its asserted verdict."""
    if "original_record" in record:
        def identities(value):
            if isinstance(value, dict):
                if set(value) == {"path", "sha256"}:
                    return value["sha256"]
                return {key: identities(item) for key, item in value.items()}
            if isinstance(value, list):
                return [identities(item) for item in value]
            return value

        original = _read_bound(record["original_record"])
        if identities(original) != identities({key: value for key, value in record.items() if key != "original_record"}):
            raise ValueError("Retained V03 calibration differs from the original")
    if (record.get("kind") != "v03_isolation_calibration_v3"
            or frozen.get("calibration_controls") != CALIBRATION_CONTROLS
            or frozen.get("calibration_order_tests") != list(CALIBRATION_ORDER_TESTS)
            or frozen.get("calibration_wall_seconds") != CALIBRATION_WALL_SECONDS
            or frozen.get("max_workers") != MAX_MUTATION_WORKERS
            or record.get("command") != [frozen["python"], "-m", "mutmut", "run",
                                          "--max-children", str(MAX_MUTATION_WORKERS), *CALIBRATION_CONTROLS]
            or record.get("source_digest") != frozen["source_digest"]):
        raise ValueError("V03 calibration differs from its frozen plan")
    listing = reconstruct_observation(_read_bound(record["raw_listing"], parse=False),
                                      record["raw_metadata"], record["listing_returncode"])
    _read_bound(record["listing_stderr"], parse=False)
    log = _read_bound(record["log"], parse=False)
    if (not same_test_data(frozen["test_data_inputs"], record["test_data_inputs"])
            or listing.get("inventory_error") or listing.get("missing_raw_modules")
            or record.get("end_dependencies") != frozen["dependencies"]
            or record.get("end_source_digest") != frozen["source_digest"]
            or record.get("returncode") != 0 or record.get("timed_out") is not False
            or record.get("elapsed_seconds", -1) < 0
            or record.get("elapsed_seconds", float("inf")) > CALIBRATION_WALL_SECONDS + 12):
        return False
    order = record.get("clean_order", {})
    if (order.get("command") != [frozen["python"], "-m", "pytest", "-q", *CALIBRATION_ORDER_TESTS,
                                  "--junitxml=../calibration/order-tests.xml"]
            or order.get("returncode") != 0 or order.get("timed_out") is not False):
        return False
    _read_bound(order["log"], parse=False)
    cases = list(ET.fromstring(_read_bound(order["junit"], parse=False)).iter("testcase"))
    expected_order = [(node.split("::")[0].removesuffix(".py").replace("/", "."),
                       node.split("::")[-1]) for node in CALIBRATION_ORDER_TESTS]
    if (len(cases) != len(CALIBRATION_ORDER_TESTS)
            or any(any(child.tag in {"failure", "error", "skipped"} for child in case) for case in cases)
            or [(case.get("classname"), case.get("name")) for case in cases] != expected_order):
        return False
    statuses = {row["id"]: row["status"] for row in listing["mutants"]}
    if (any(statuses.get(mid) != control["status"] for mid, control in CALIBRATION_CONTROLS.items())
            or any(status != "not checked" for mid, status in statuses.items() if mid not in CALIBRATION_CONTROLS)
            or not set(IN_SCOPE_MODULES) <= {row["module"] for row in listing["mutants"]}
            or not all(marker in log for marker in ("Running stats", "Running clean tests",
                                                    "Running forced fail test", "Running mutation testing"))):
        return False
    if "stats" not in record:
        return False
    stats = _read_bound(record["stats"])
    selected = stats.get("tests_by_mangled_function_name", {}).get(CALIBRATION_FUNCTION)
    if not selected or not all(test in stats.get("duration_by_test", {}) for test in selected):
        return False
    if set(record.get("control_diffs", {})) != set(CALIBRATION_CONTROLS):
        return False
    for mid, control in CALIBRATION_CONTROLS.items():
        diff = _read_bound(record["control_diffs"][mid], parse=False)
        removed = [line[1:] for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]
        added = [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
        if removed != [control["removed"]] or added != [control["added"]]:
            return False
    return True


def calibrate_isolation(workspace, frozen):
    """Run fixed controls in the exact campaign workspace before the full run."""
    from validation.evidence import ROOT, source_digest

    directory = workspace / "calibration"
    directory.mkdir(exist_ok=False)
    command = [sys.executable, "-m", "mutmut", "run", "--max-children", str(MAX_MUTATION_WORKERS), *CALIBRATION_CONTROLS]
    started = time.monotonic()
    code, timed_out = 0, False
    with (directory / "execution.log").open("x") as log:
        try:
            timed_out = not _run_with_deadline(command, cwd=workspace,
                env=dict(os.environ, GIT_DIR=str(ROOT / ".git")),
                timeout=CALIBRATION_WALL_SECONDS, stdout=log)
            if timed_out:
                code = None
        except subprocess.CalledProcessError as exc:
            code = exc.returncode
    order = {}
    if code == 0 and not timed_out:
        order_command = [sys.executable, "-m", "pytest", "-q", *CALIBRATION_ORDER_TESTS,
                         "--junitxml=../calibration/order-tests.xml"]
        order_code, order_timed_out = 0, False
        with (directory / "order.log").open("x") as log:
            try:
                order_timed_out = not _run_with_deadline(order_command, cwd=workspace / "mutants",
                    env=dict(os.environ, GIT_DIR=str(ROOT / ".git"), MUTANT_UNDER_TEST=""),
                    timeout=max(1, CALIBRATION_WALL_SECONDS - (time.monotonic() - started)), stdout=log)
            except subprocess.CalledProcessError as exc:
                order_code = exc.returncode
        order = {"command": order_command, "returncode": order_code, "timed_out": order_timed_out,
                 "log": _binding(directory / "order.log")}
        if (directory / "order-tests.xml").exists():
            order["junit"] = _binding(directory / "order-tests.xml")
    elapsed = time.monotonic() - started
    listing_process = subprocess.run([sys.executable, "-m", "mutmut", "results", "--all", "true"],
                                     cwd=workspace, capture_output=True, text=True)
    with (directory / "individual-results.txt").open("x") as handle:
        handle.write(listing_process.stdout)
    with (directory / "listing-stderr.txt").open("x") as handle:
        handle.write(listing_process.stderr)
    metadata = []
    for entry in raw_metadata_bindings(workspace):
        retained = directory / "metadata" / (entry["module"].replace(".", "/") + ".py.meta")
        retained.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry["binding"]["path"], retained)
        metadata.append({"module": entry["module"], "binding": _binding(retained)})
    test_inputs = []
    for entry in test_data_inventory(workspace / "mutants"):
        retained = directory / "test-inputs" / entry["relative_path"]
        retained.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry["binding"]["path"], retained)
        test_inputs.append({"relative_path": entry["relative_path"], "binding": _binding(retained)})
    record = {"kind": "v03_isolation_calibration_v3", "command": command,
              "source_digest": frozen["source_digest"], "end_source_digest": source_digest(workspace),
              "end_dependencies": dependency_versions(),
              "returncode": code, "timed_out": timed_out, "elapsed_seconds": elapsed,
              "clean_order": order,
              "listing_returncode": listing_process.returncode,
              "listing_stderr": _binding(directory / "listing-stderr.txt"), "raw_metadata": metadata,
              "test_data_inputs": test_inputs,
              "log": _binding(directory / "execution.log"),
              "raw_listing": _binding(directory / "individual-results.txt")}
    stats = workspace / "mutants/mutmut-stats.json"
    if stats.exists():
        shutil.copyfile(stats, directory / "stats.json")
        record["stats"] = _binding(directory / "stats.json")
    record["control_diffs"] = {}
    for number, mid in enumerate(CALIBRATION_CONTROLS):
        diff = subprocess.run([sys.executable, "-m", "mutmut", "show", mid], cwd=workspace,
                              capture_output=True, text=True)
        if diff.returncode == 0:
            path = directory / f"control-{number}.diff"
            with path.open("x") as handle:
                handle.write(diff.stdout)
            record["control_diffs"][mid] = _binding(path)
    record["passed"] = verify_calibration(record, frozen)
    path = directory / "result.json"
    _write_once(path, record)
    print(f"Mutation isolation calibration: {'PASS' if record['passed'] else 'FAIL'} ({elapsed:.1f}s)", flush=True)
    return record, _binding(path)


def verify_execution_artifacts(result):
    """Rebuild individual statuses and verify actual frozen files, never labels."""
    from validation.evidence import ROOT
    from validation.v03_equivalence import RULES, verify_certificate

    read = _read_bound
    frozen = read(result["execution_freeze"])
    if (frozen.get("kind") != "v03_execution_freeze_v8"
            or frozen.get("raw_outcome_policy") != RAW_OUTCOME_POLICY
            or frozen.get("source_digest") != result.get("source_digest")
            or frozen.get("required_modules") != IN_SCOPE_MODULES
            or frozen.get("critical_paths") != list(CRITICAL_PATHS)
            or frozen.get("tool_version") != "3.8.0"
            or frozen.get("max_workers") != MAX_MUTATION_WORKERS
            or frozen.get("wall_seconds") != MAX_CAMPAIGN_WALL_SECONDS
            or frozen.get("dependencies") != dependency_versions()
            or frozen.get("library_ownership") != library_ownership(ROOT)
            or not frozen.get("tool_sources") or frozen.get("equivalence_rules") != list(RULES)):
        raise ValueError("V03 execution freeze differs from the current phase")
    verify_frozen_tool_sources(frozen["tool_sources"], frozen.get("tool_source_manifest"))
    if (_read_bound(frozen["resource_policy"]) != resource_policy()
            or frozen["resource_policy"]["sha256"] != _binding(POLICY_PATH)["sha256"]):
        raise ValueError("V03 measured resource policy differs from its freeze")
    for binding in frozen["tool_sources"] + [frozen[key] for key in ("config_file", "protocol", "protocol_register", "equivalence_argument")]:
        read(binding, parse=False)
    if frozen["equivalence_argument"]["sha256"] != _binding(ROOT / "docs/program/MUTATION_EQUIVALENCE_LEMMAS_2026_10_23.md")["sha256"]:
        raise ValueError("V03 equivalence argument differs from the frozen rules")
    # The program is a retained test-context snapshot, not executable source.
    # New master receipts may follow execution; static fixture bytes may not.
    def static_inputs(rows):
        return [row for row in rows if row["relative_path"] != "docs/program/program.json"]

    if not same_test_data(static_inputs(frozen["test_data_inputs"]), static_inputs(test_data_inventory(ROOT))):
        raise ValueError("V03 non-Python test inputs differ from the frozen phase")
    tested_data_match = same_test_data(frozen["test_data_inputs"], result["tested_data_inputs"])
    if result.get("execution_completed") is True and not tested_data_match:
        raise ValueError("V03 executed non-Python test inputs differ from the freeze")
    if result.get("execution_completed") is True and result.get("end_dependencies") != frozen["dependencies"]:
        raise ValueError("V03 runtime dependencies changed during execution")
    if "original_freeze" in frozen:
        original = read(frozen["original_freeze"])
        for key in original:
            if key == "tool_sources":
                equal = [x["sha256"] for x in original[key]] == [x["sha256"] for x in frozen[key]]
            elif key in {"config_file", "protocol", "protocol_register", "equivalence_argument", "resource_policy"}:
                equal = original[key]["sha256"] == frozen[key]["sha256"]
            elif key == "test_data_inputs":
                equal = [(r["relative_path"], r["binding"]["sha256"]) for r in original[key]] == [
                         (r["relative_path"], r["binding"]["sha256"]) for r in frozen[key]]
            else:
                equal = original[key] == frozen.get(key)
            if not equal:
                raise ValueError("Retained V03 freeze differs from the pre-execution original")
    raw = reconstruct_observation(read(result["raw_listing"], parse=False), result["raw_metadata"],
                                  result["listing_returncode"])
    read(result["listing_stderr"], parse=False)
    read(result["execution_log"], parse=False)
    for key in ("mutation_stats", "worker_log"):
        if result.get(key):
            read(result[key], parse=False)
        elif result.get("execution_completed") is True:
            raise ValueError("Completed V03 lacks raw runner evidence")
    if (raw["missing_raw_modules"] != result.get("missing_raw_modules")
            or raw["inventory_error"] != result.get("inventory_error")
            or (raw["inventory_error"] or raw["missing_raw_modules"]) and result.get("execution_completed") is True):
        raise ValueError("V03 raw metadata inventory is incomplete or misreported")
    if raw["mutants"] != result["mutants"]:
        raise ValueError("V03 results differ from the complete raw listing")
    verify_resource_execution(result, raw)
    statuses = {row["id"]: row["status"] for row in raw["mutants"]}
    for certificate in result.get("equivalent_mutants", []):
        if statuses.get(certificate["id"]) != "survived":
            raise ValueError("An equivalence proof can exclude only an observed survivor")
        verify_certificate(certificate, ROOT)
    calibrated = verify_calibration(read(result["calibration"]), frozen)
    if result.get("execution_completed") is True and not calibrated:
        raise ValueError("V03 full execution bypassed required attribution calibration")
    if calibrated and not raw["inventory_error"]:
        statuses = {row["id"]: row["status"] for row in raw["mutants"]}
        if any(statuses.get(mid) != control["status"] for mid, control in CALIBRATION_CONTROLS.items()):
            raise ValueError("V03 final control outcomes differ from calibration")
    return frozen


def verify_resource_execution(result, raw):
    """Reconstruct the complete scheduling manifest and actual admission trace."""
    from types import SimpleNamespace
    from validation.v03_resource_scheduler import verify_schedule, verify_trace

    if not result.get("resource_schedule"):
        if result.get("execution_completed") is True:
            raise ValueError("Completed V03 lacks its frozen resource schedule")
        return
    scheduled = _read_bound(result["resource_schedule"])
    stats = _read_bound(result["mutation_stats"])
    rows = verify_schedule(scheduled, stats, raw, SimpleNamespace(
        timeout_constant=MUTANT_TIMEOUT_CONSTANT, timeout_multiplier=MUTANT_TIMEOUT_MULTIPLIER))
    if scheduled.get("precompleted") != sorted(CALIBRATION_CONTROLS):
        raise ValueError("V03 resource schedule reused uncalibrated outcomes")
    if result.get("resource_trace"):
        trace = [json.loads(line) for line in _read_bound(result["resource_trace"], parse=False).splitlines()]
        if result.get("execution_completed") is True:
            codes = {row["id"]: row["raw_exit_code"] for row in raw["mutants"]}
            verify_trace(trace, [row for row in rows if row["mutant"] not in CALIBRATION_CONTROLS], codes)
    elif result.get("execution_completed") is True:
        raise ValueError("Completed V03 lacks its actual resource trace")


def retain_execution_artifacts(result, artifact_dir):
    """Keep exact bytes under the audited run so evidence survives /tmp cleanup."""
    target = Path(artifact_dir) / "mutation"
    target.mkdir(parents=True, exist_ok=False)
    frozen = json.loads(Path(result["execution_freeze"]["path"]).read_text())

    def retain(binding, relative):
        source = Path(binding["path"])
        if _binding(source) != binding:
            raise ValueError("V03 input changed before evidence retention")
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        return _binding(dest)

    original = retain(result["execution_freeze"], "original-execution-freeze.json")
    frozen["original_freeze"] = original
    frozen["tool_sources"] = [retain(ref, f"tool/{i:03d}.py")
                              for i, ref in enumerate(frozen["tool_sources"])]
    for key in ("config_file", "protocol", "protocol_register", "equivalence_argument", "resource_policy"):
        frozen[key] = retain(frozen[key], key + ".txt")
    frozen["test_data_inputs"] = [{"relative_path": row["relative_path"],
        "binding": retain(row["binding"], "frozen-test-inputs/" + row["relative_path"])}
        for row in frozen["test_data_inputs"]]
    path = target / "execution-freeze.json"
    _write_once(path, frozen)
    result["execution_freeze"] = _binding(path)
    result["raw_listing"] = retain(result["raw_listing"], "individual-results.txt")
    result["listing_stderr"] = retain(result["listing_stderr"], "listing-stderr.txt")
    result["execution_log"] = retain(result["execution_log"], "execution.log")
    result["raw_metadata"] = [{"module": row["module"],
        "binding": retain(row["binding"], "metadata/" + row["module"].replace(".", "/") + ".py.meta")}
        for row in result["raw_metadata"]]
    result["tested_data_inputs"] = [{"relative_path": row["relative_path"],
        "binding": retain(row["binding"], "executed-test-inputs/" + row["relative_path"])}
        for row in result["tested_data_inputs"]]
    for key, name in (("mutation_stats", "mutmut-stats.json"), ("worker_log", "mutmut-debug.log"),
                      ("resource_schedule", "mutmut-schedule.json"),
                      ("resource_trace", "mutmut-schedule-trace.jsonl")):
        if result.get(key):
            result[key] = retain(result[key], name)
    record = _read_bound(result["calibration"])
    for key in ("log", "raw_listing", "listing_stderr", "stats"):
        if key in record:
            record[key] = retain(record[key], "calibration/" + key)
    record["raw_metadata"] = [{"module": row["module"],
        "binding": retain(row["binding"], "calibration/metadata/" + row["module"].replace(".", "/") + ".py.meta")}
        for row in record["raw_metadata"]]
    record["test_data_inputs"] = [{"relative_path": row["relative_path"],
        "binding": retain(row["binding"], "calibration/test-inputs/" + row["relative_path"])}
        for row in record["test_data_inputs"]]
    record["control_diffs"] = {mid: retain(ref, f"calibration/control-{i}.diff")
                               for i, (mid, ref) in enumerate(record["control_diffs"].items())}
    for key in ("log", "junit"):
        if key in record.get("clean_order", {}):
            record["clean_order"][key] = retain(record["clean_order"][key], "calibration/order-" + key)
    record["original_record"] = retain(result["calibration"], "calibration/original-result.json")
    path = target / "calibration/result.json"
    _write_once(path, record)
    result["calibration"] = _binding(path)
    retained_sources = {}
    for certificate in result.get("equivalent_mutants", []):
        ref = certificate["generated_source"]
        if ref["path"] not in retained_sources:
            retained_sources[ref["path"]] = retain(ref, "generated/" + certificate["source_path"])
        certificate["generated_source"] = retained_sources[ref["path"]]
    return result


def collect_equivalence_proofs(results, workspace):
    """Apply only the prospectively frozen exact lemmas to actual survivors."""
    from validation.v03_equivalence import RULES, verify_certificate

    proofs, modules = [], {}
    for row in results["mutants"]:
        if row["status"] != "survived":
            continue
        path = row["module"].replace(".", "/") + ".py"
        if path not in modules:
            generated = workspace / "mutants" / path
            spans = json.loads(Path(str(generated) + ".spans").read_text())["spans"]
            modules[path] = (_binding(generated), spans, _binding(workspace / path)["sha256"])
        binding, spans, source_hash = modules[path]
        name = row["id"].rsplit(".", 1)[-1]
        original = name.split("__mutmut_", 1)[0] + "__mutmut_orig"
        certificate = {"id": row["id"], "source_path": path, "source_sha256": source_hash,
                       "generated_source": binding, "original_span": spans[original], "mutated_span": spans[name]}
        for rule in RULES:
            certificate["rule"] = rule
            try:
                verify_certificate(certificate, workspace)
            except ValueError:
                continue
            proofs.append(dict(certificate))
            break
    return proofs


def prepare_mutation_workspace():
    """Copy executable inputs and the immutable fixtures used by today's tests."""
    import shutil
    import tempfile
    from validation.evidence import ROOT

    workspace = Path(tempfile.mkdtemp(prefix="hponas-v03-"))
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mutmut"]
    inputs = dict.fromkeys(["hponas", "workloads", "validation", "tools", "tests", "examples",
                           *config["also_copy"]])
    for name in inputs:
        source = ROOT / name
        target = workspace / name
        if Path(name).is_absolute() or ".." in Path(name).parts or not source.resolve().is_relative_to(ROOT):
            raise ValueError("Mutation workspace input escapes the source root")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target,
                            ignore=shutil.ignore_patterns("__pycache__", "artifacts", "results"))
        else:
            shutil.copy2(source, target)
            # mutmut 3.8 copies explicit files without creating their parents.
            # Prepare only directories; actual test-input copies remain tool-owned.
            (workspace / "mutants" / name).parent.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.toml", "*.txt", "*.md"):
        for path in ROOT.glob(pattern):
            shutil.copy2(path, workspace / path.name)
    print(f"Fresh mutation workspace: {workspace}", flush=True)
    return workspace


def run_mutmut() -> dict:
    """Execute in a new source copy; retain every prior cache and interruption."""
    from validation.evidence import ROOT, source_digest

    workspace = prepare_mutation_workspace()
    snapshot_digest = source_digest(workspace)
    frozen = mutation_freeze(workspace)
    freeze_path = workspace / "execution-freeze.json"
    _write_once(freeze_path, frozen)
    started = time.monotonic()
    calibration, calibration_binding = calibrate_isolation(workspace, frozen)
    execution_error = None
    if not calibration["passed"]:
        completed = False
        execution_error = "Required mutation isolation calibration failed"
        with (workspace / "execution.log").open("x") as log:
            log.write(execution_error + "; full invocation not launched\n")
    else:
        try:
            with (workspace / "execution.log").open("x") as log:
                completed = _run_with_deadline(
                    [sys.executable, "-m", "mutmut", "run", "--max-children", str(MAX_MUTATION_WORKERS)],
                    cwd=workspace,
                    env=dict(os.environ, GIT_DIR=str(ROOT / ".git"), HPONAS_V03_SCHEDULING="measured_v1"),
                    timeout=max(1, MAX_CAMPAIGN_WALL_SECONDS - (time.monotonic() - started)), stdout=log,
                )
        except subprocess.CalledProcessError as exc:
            # Preserve failures; a failed clean suite is never a mutant kill.
            completed = False
            execution_error = f"mutmut run exited {exc.returncode}"
    listing_process = subprocess.run([sys.executable, "-m", "mutmut", "results", "--all", "true"],
                                     cwd=workspace, capture_output=True, text=True)
    listing = listing_process.stdout
    listing_path = workspace / "individual-results.txt"
    with listing_path.open("x") as handle:
        handle.write(listing)
    with (workspace / "listing-stderr.txt").open("x") as handle:
        handle.write(listing_process.stderr)
    metadata = raw_metadata_bindings(workspace)
    result = reconstruct_observation(listing, metadata, listing_process.returncode)
    result["listing_returncode"] = listing_process.returncode
    result["listing_stderr"] = _binding(workspace / "listing-stderr.txt")
    result["raw_metadata"] = metadata
    for key, name in (("mutation_stats", "mutmut-stats.json"), ("worker_log", "mutmut-debug.log"),
                      ("resource_schedule", "mutmut-schedule.json"),
                      ("resource_trace", "mutmut-schedule-trace.jsonl")):
        path = workspace / "mutants" / name
        result[key] = _binding(path) if path.is_file() else None
    result["equivalent_mutants"] = collect_equivalence_proofs(result, workspace)
    result["execution_freeze"] = _binding(freeze_path)
    result["raw_listing"] = _binding(listing_path)
    result["execution_log"] = _binding(workspace / "execution.log")
    result["calibration"] = calibration_binding
    result["workspace"] = str(workspace)
    result["source_digest"] = snapshot_digest
    result["end_dependencies"] = dependency_versions()
    result["tested_data_inputs"] = test_data_inventory(workspace / "mutants")
    data_match = same_test_data(frozen.get("test_data_inputs", []), result["tested_data_inputs"])
    result["execution_completed"] = completed and not result["inventory_error"] and not result["missing_raw_modules"] and all(
        result.get(key) for key in ("mutation_stats", "worker_log", "resource_schedule", "resource_trace")) and data_match and (
        frozen.get("dependencies") == result["end_dependencies"]) and not any(
        m["status"] in UNRESOLVED_STATUSES for m in result["mutants"])
    result["execution_error"] = execution_error
    result["snapshot_end_source_digest"] = source_digest(workspace)
    return result


def campaign(run=False, equivalents=None, artifact_dir=None):
    from validation.evidence import source_digest

    before = source_digest()
    if run and equivalents:
        raise ValueError("Fresh V03 derives proofs from its generated population; external exclusions are forbidden")
    raw = run_mutmut() if run else parse_mutmut_results()
    if run and artifact_dir is not None:
        raw = retain_execution_artifacts(raw, artifact_dir)
    proofs = raw.get("equivalent_mutants", []) if run else equivalents or []
    analysis = analyze_results(raw, proofs)
    after = source_digest()
    snapshot_digest = raw.get("source_digest") if run else None
    completed = raw.get("execution_completed", False)
    fresh = run and before == snapshot_digest == after == raw.get("snapshot_end_source_digest")
    return {
        "validation_id": "V03",
        "schema_version": 2,
        "tool": "mutmut",
        "tool_version": importlib.metadata.version("mutmut"),
        "fresh_campaign": fresh,
        "record_type": "fresh_execution" if run else "imported_diagnostic",
        "execution_completed": completed,
        "execution_error": raw.get("execution_error"),
        # Preserve the executed source identity even if the live tree changes.
        # The gate still rejects it as current certification in that case.
        "source_digest": snapshot_digest,
        "end_source_digest": after,
        "snapshot_end_source_digest": raw.get("snapshot_end_source_digest"),
        "end_dependencies": raw.get("end_dependencies"),
        "workspace": raw.get("workspace"),
        "execution_freeze": raw.get("execution_freeze"),
        "raw_listing": raw.get("raw_listing"),
        "listing_returncode": raw.get("listing_returncode"),
        "listing_stderr": raw.get("listing_stderr"),
        "inventory_error": raw.get("inventory_error"),
        "raw_metadata": raw.get("raw_metadata"),
        "tested_data_inputs": raw.get("tested_data_inputs"),
        "mutation_stats": raw.get("mutation_stats"),
        "worker_log": raw.get("worker_log"),
        "resource_schedule": raw.get("resource_schedule"),
        "resource_trace": raw.get("resource_trace"),
        "missing_raw_modules": raw.get("missing_raw_modules", []),
        "execution_log": raw.get("execution_log"),
        "calibration": raw.get("calibration"),
        "mutants": raw["mutants"],
        "equivalent_mutants": proofs,
        "overall": analysis,
        "per_module": analysis["per_module"],
        "critical_survivors": analysis["critical_survivors"],
        "passed": fresh and completed and inventory_verdict(raw, analysis) == "PASS",
        "verdict": inventory_verdict(raw, analysis)
        if fresh and completed
        else "INCONCLUSIVE",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--equivalents", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("validation/results/v03_results.json")
    )
    args = parser.parse_args()
    eq = json.loads(args.equivalents.read_text()) if args.equivalents else []
    result = campaign(args.run, eq)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("mutants", "per_module")},
            indent=2,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
