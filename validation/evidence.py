"""Campaign identity and independently recomputed Tier 0 decisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from tools.source_identity import source_digest

ROOT = Path(__file__).resolve().parents[1]
TIER0 = ("V01", "V02", "V03", "V04-T0", "V05", "V14")


class AuditContextError(RuntimeError):
    """Audited evidence requires the complete, identifiable source checkout."""


def require_audit_checkout():
    """Reject absent repository provenance before campaign work or writes.

    A wheel omits tests and build inputs hashed by source_digest. Never
    substitute a wheel hash or an unrelated current-directory checkout.
    """
    message = (
        "Audited campaigns require a full HPO-NAS Git checkout with tests, "
        "examples, dependency files and protocols. Install its dependencies, "
        "then run `python -m validation.run_validation_with_audit` from that "
        "checkout. For installed-wheel checks use `python -m tools.check_installed "
        "--output receipt.json`; those checks do not certify a campaign."
    )
    required_files = ("pyproject.toml", "requirements.txt", "validation/protocols.json")
    required_dirs = ("hponas", "workloads", "validation/protocols", "tools", "tests", "examples")
    if any(not (ROOT / name).is_file() for name in required_files) or any(
        not (ROOT / name).is_dir() for name in required_dirs
    ):
        raise AuditContextError(message)
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True,
            stderr=subprocess.PIPE,
        ).strip()
        if Path(top).resolve() != ROOT.resolve():
            raise AuditContextError(message)
        return subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AuditContextError(message) from exc


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _installed(name):
    import importlib.metadata

    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def metadata(validation_id):
    import importlib.metadata
    import platform
    from datetime import datetime, timezone

    revision = require_audit_checkout()
    return {
        "validation_id": validation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_digest": source_digest(),
        "python": platform.python_version(),
        "version": revision,
        "packages": {
            n: importlib.metadata.version(n)
            for n in ("numpy", "scipy", "torch", "botorch", "gpytorch", "cloudpickle")
        },
        "optional_packages": {
            n: {
                "version": importlib.metadata.version(n),
                "source": importlib.metadata.distribution(n).read_text(
                    "direct_url.json"
                ),
            }
            for n in ("jax", "brax", "ray", "optuna", "pytest", "mutmut")
            if _installed(n)
        },
    }


def _finite_vector(values, minimum=1):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < minimum or not np.isfinite(x).all():
        raise ValueError("Missing, nonfinite or undersized observations")
    return x


def decision(validation_id: str, result: dict) -> str:
    """Ignore supplied PASS/threshold fields. Unknown schemas cannot certify a gate."""
    if validation_id == 'V12':
        from validation.warm_finite_campaign import CLAIM as WARM_CLAIM, reconstruct
        if result.get('claim') != WARM_CLAIM or result.get('schema_version') != 1:
            return 'INCONCLUSIVE'
        return reconstruct(result)['verdict']
    if validation_id == 'V07':
        from validation.dehb_finite import CLAIM as DEHB_CLAIM, reconstruct
        if result.get('claim') != DEHB_CLAIM or result.get('schema_version') != 1:
            return 'INCONCLUSIVE'
        return reconstruct(result)['verdict']
    if validation_id == 'V15a':
        from validation.ifbo_finite_contract import CLAIM as IFBO_CLAIM
        if result.get('claim') != IFBO_CLAIM or result.get('schema_version') != 1:
            return 'INCONCLUSIVE'
        from validation.ifbo_finite_campaign import recompute_result
        return recompute_result(result)
    if validation_id == 'V08':
        from validation.population_contract import CLAIM as POPULATION_CLAIM
        if result.get('claim') != POPULATION_CLAIM or result.get('schema_version') != 1:
            return 'INCONCLUSIVE'
        from validation.population_campaign import recompute_result
        return recompute_result(result)
    from validation.tier1_contract import ENTRIES as TIER1, CLAIM
    if validation_id in TIER1:
        if result.get('claim') != CLAIM or result.get('schema_version') != 1:
            return 'INCONCLUSIVE'
        from validation.tier1_campaign import recompute_result
        return recompute_result(validation_id, result)
    if validation_id == "V01" and result.get("schema_version") == 2:
        from validation.v01_finite_campaign import recompute_result

        return recompute_result(result)
    if validation_id == "V02" and result.get("schema_version") == 2:
        from validation.v02_final_campaign import recompute_result

        return recompute_result(result)
    if validation_id in {"V04-T0", "V05"} and result.get("schema_version") == 4:
        from validation.stylized_campaign import recompute_result

        return recompute_result(validation_id, result)
    if validation_id in {"V04-T0", "V05"} and result.get("schema_version") == 3:
        if result.get("validation_id") != validation_id:
            raise ValueError("Unrecognized validation identity")
        # Historical comparison evidence cannot certify the prospectively
        # adopted v4 finite-conformance contract. Its raw verifier is retained
        # in tier0_rank_campaign for historical analysis only.
        return "INCONCLUSIVE"
    if validation_id in {"V04-T0", "V05"} and result.get("schema_version") == 2:
        if result.get("validation_id") != validation_id:
            raise ValueError("Unrecognized validation identity")
        return "INCONCLUSIVE"
    if (
        result.get("schema_version") not in ((1, 2) if validation_id == "V03" else (1,))
        or result.get("validation_id") != validation_id
    ):
        raise ValueError("Unrecognized validation identity/schema")
    if result.get("blocked_reason"):
        return "BLOCKED"
    if validation_id == "V03":
        from validation.v03_mutation_testing import analyze_results, inventory_verdict, verify_execution_artifacts

        if (
            not result.get("fresh_campaign")
            or result.get("source_digest") != source_digest()
        ):
            return "INCONCLUSIVE"
        verify_execution_artifacts(result)
        if (result.get("execution_completed") is not True
                or result.get("snapshot_end_source_digest") != result.get("source_digest")
                or result.get("end_source_digest") != result.get("source_digest")):
            return "INCONCLUSIVE"
        analysis = analyze_results(result, result.get("equivalent_mutants", []))
        return inventory_verdict(result, analysis)
    if validation_id == "V01":
        comparisons = result.get("comparisons", [])
        if not comparisons or {c["component"] for c in comparisons} != {
            "GP",
            "Sobol",
            "TPE",
        }:
            raise ValueError("GP, Sobol and TPE vendor comparisons required")
        sobol = [c for c in comparisons if c["component"] == "Sobol"]
        if len(comparisons) != 7 or {c.get("dimension") for c in sobol} != set(
            range(5)
        ):
            raise ValueError("Five Sobol dimensions and one GP/TPE comparison required")
        for c in comparisons:
            if (
                c.get("reference")
                != {"GP": "botorch", "Sobol": "scipy", "TPE": "optuna"}[c["component"]]
            ):
                raise ValueError("Independent vendor reference required")
            ours = _finite_vector(
                c["actual"], 1000 if c["component"] == "Sobol" else 30
            )
            reference = _finite_vector(
                c["reference_values"], 1000 if c["component"] == "Sobol" else 30
            )
            if ours.shape != reference.shape or not np.allclose(ours, reference, rtol=1e-10, atol=1e-12):
                return "FAIL"
        if result.get("evidence_kind") == "synthetic_wrapper_wiring":
            from validation.v01_wrapper_checks import verify_wrappers

            if not verify_wrappers(result.get("wrapper_checks", [])):
                return "FAIL"
        # Exact synthetic wiring checks do not establish the registered
        # finite-corpus claim adopted in protocol 2.0. They lack that complete
        # frozen inventory, source bindings and independent raw reconstruction.
        return "INCONCLUSIVE"
    if validation_id == "V02":
        scenarios = result.get("scenarios", [])
        required = {
            "gp_replay",
            "asha_replay",
            "crash_resume",
            "concurrent_replay",
            "adversarial_events",
            "non_vacuity",
        }
        if result.get("evidence_kind") in {"candidate_event_grammar", "bound_candidate_event_grammar"}:
            required.add("streamed_replay")
            required.add("cancelled_replay")
        if len(scenarios) != len(required) or {s["id"] for s in scenarios} != required:
            raise ValueError("Complete unique V02 scenario inventory required")
        if result.get("evidence_kind") == "bound_candidate_event_grammar":
            from validation.v02_contract import verify_bound_result
            from validation.v02_raw_reconstruction import verify_crash, verify_concurrency

            if not verify_bound_result(result):
                return "FAIL"
            by_id = {scenario["id"]: scenario for scenario in scenarios}
            # Reconstruct from raw checkpoints, worker journals, vendor RNG and
            # the objective formula. Caller-supplied expected/actual pairs do
            # not establish process recovery or concurrent outcome correctness.
            verify_crash(result["run_dir"], by_id["crash_resume"])
            verify_concurrency(result["run_dir"], by_id["concurrent_replay"])
        required_runs = {
            "gp_replay": (20, 42),
            "asha_replay": (30, 43),
            "crash_resume": (50, 44),
            "concurrent_replay": (20, 45),
            "streamed_replay": (2, 47),
            "cancelled_replay": (1, 48),
        }
        for scenario in scenarios:
            if scenario["id"] in required_runs:
                if (scenario.get("n_trials"), scenario.get("seed")) != required_runs[
                    scenario["id"]
                ]:
                    raise ValueError(
                        "V02 scenario budget or seed differs from protocol"
                    )
            if scenario["id"] in {"gp_replay", "asha_replay", "concurrent_replay", "streamed_replay", "cancelled_replay"}:
                from hponas import GPSearcher, RandomSearcher
                from hponas.events import EventLog
                from hponas.replay import ReplayEngine
                from hponas.schedulers import ASHAScheduler, ASHAConfig
                from validation.v02_state_replay import _space

                artifact = scenario["event_log"]
                if digest(artifact["path"]) != artifact["sha256"]:
                    raise ValueError("Changed V02 event log")
                constructor = (
                    GPSearcher if scenario["id"] == "gp_replay" else RandomSearcher
                )
                scheduler = (
                    ASHAScheduler(ASHAConfig(**scenario["scheduler_config"]))
                    if scenario.get("scheduler_config")
                    else None
                )
                engine = ReplayEngine(
                    constructor(_space(), seed=scenario["seed"]),
                    EventLog(artifact["path"]),
                    scenario["seed"],
                    scheduler,
                )
                if not engine.verify_determinism(scenario["n_trials"])[0]:
                    return "FAIL"
                if scenario["id"] in {"streamed_replay", "cancelled_replay"}:
                    required_status = "completed" if scenario["id"] == "streamed_replay" else "cancelled"
                    terminal = engine.scheduler._terminal
                    if len(terminal) != scenario["n_trials"] or set(terminal.values()) != {required_status}:
                        return "FAIL"
            if (result.get("evidence_kind") == "bound_candidate_event_grammar"
                    and scenario["id"] in {"crash_resume", "concurrent_replay"}):
                continue  # Already independently reconstructed above.
            cases = scenario.get("cases", [])
            if not cases:
                raise ValueError("Empty V02 scenario")
            for case in cases:
                if "expected" not in case or "actual" not in case:
                    raise ValueError("Missing replay evidence")
                if case["expected"] != case["actual"]:
                    return "FAIL"
        if result.get("evidence_kind") == "candidate_event_grammar":
            from validation.v02_event_grammar import verify_population

            if not verify_population(result.get("event_population", {})):
                return "FAIL"
        # The old six scenarios did not meet the registered event population.
        # Candidate grammar still needs the final protocol/population freeze.
        return "INCONCLUSIVE"
    if validation_id in {"V04-T0", "V05"}:
        # Schema 1 compared random against pathological PPO. D-T0-CLAIMS
        # explicitly preserves those observations as historical diagnostics;
        # no result, however favorable, establishes either registered claim.
        return "INCONCLUSIVE"

    if validation_id == "V14":
        if result.get("workload") != "brax_ppo" or not result.get("real_workload"):
            return "INCONCLUSIVE"
        trials = result.get("trials", [])
        if not trials:
            raise ValueError("No executed trials")
        protected = result["protected_seed"]
        if protected != 999 or result["duration_seconds"] > 60:
            return "FAIL"
        if not result["database_seeds"] or protected in result["database_seeds"]:
            return "FAIL"
        import sqlite3

        for key in ("database", "study_checkpoint"):
            if digest(result[key]["path"]) != result[key]["sha256"]:
                return "FAIL"
        with sqlite3.connect(
            f"file:{result['database']['path']}?mode=ro", uri=True
        ) as db:
            rows = db.execute(
                "SELECT trial_id,seed,value,status FROM trials"
            ).fetchall()
        if len(rows) != len(trials) or {r[1] for r in rows} != set(
            result["database_seeds"]
        ):
            return "FAIL"
        observed = {r["trial_id"]: r for r in trials}
        if any(
            tid not in observed
            or seed != observed[tid]["training_seed"]
            or value != observed[tid]["observed_value"]
            or status != "completed"
            for tid, seed, value, status in rows
        ):
            return "FAIL"
        for trial in trials:
            _finite_vector([trial["search_value"], trial["acceptance_value"]])
            if trial["training_seed"] == protected or trial["search_seed"] == protected:
                return "FAIL"
            if trial["observed_value"] != trial["search_value"]:
                return "FAIL"
            for key in ("checkpoint", "learning_curve"):
                artifact = Path(trial[key]["path"])
                if (
                    not artifact.is_file()
                    or artifact.stat().st_size == 0
                    or digest(artifact) != trial[key]["sha256"]
                ):
                    return "FAIL"
        return "PASS"
    raise ValueError(f"No result evaluator registered for {validation_id}")


def historical_ppo_diagnostic_decision(validation_id, result):
    """Recompute the old experiment for inspection only; never used by a gate."""
    if validation_id in {"V04-T0", "V05"}:
        from scipy.stats import mannwhitneyu

        if (
            result.get("workload") != "brax_ppo"
            or not result.get("real_workload")
            or result.get("smoke")
        ):
            return "INCONCLUSIVE"
        seeds = list(range(5 if validation_id == "V04-T0" else 3))
        if result.get("seeds") != seeds or result.get("n_trials") != 50:
            raise ValueError("Campaign seed set and trial budget differ from protocol")
        expected_aucs = {"random": [], "pathological": []}
        curves = result.get("curves", [])
        if len(curves) != 2 * len(seeds):
            raise ValueError("Missing baseline curves")
        for arm in expected_aucs:
            for seed in seeds:
                matches = [c for c in curves if c["seed"] == seed and c["arm"] == arm]
                if len(matches) != 1:
                    raise ValueError("Missing or duplicate baseline curve")
                curve = matches[0]
                values = _finite_vector(curve["values"], 50)
                if len(values) != 50:
                    raise ValueError("Unexpected trial count")
                receipts = curve["receipts"]
                if digest(receipts["path"]) != receipts["sha256"]:
                    raise ValueError("Changed trial receipts")
                saved = json.loads(Path(receipts["path"]).read_text())
                if [r["value"] for r in saved] != values.tolist():
                    raise ValueError("Trial values differ from receipt")
                if any(r["metadata"]["workload"] != "brax_ppo" for r in saved):
                    raise ValueError("Non-RL trial")
                expected_aucs[arm].append(
                    float(np.trapezoid(np.maximum.accumulate(values)) / len(values))
                )
        if (
            expected_aucs["random"] != result["random_aucs"]
            or expected_aucs["pathological"] != result["pathological_aucs"]
        ):
            raise ValueError("AUCs differ from raw trial curves")
        random = _finite_vector(result["random_aucs"], len(seeds))
        baseline = _finite_vector(result["pathological_aucs"], len(seeds))
        if abs(baseline.mean()) < 1e-12:
            return "INCONCLUSIVE"
        improvement = (random.mean() - baseline.mean()) / abs(baseline.mean())
        p = mannwhitneyu(random, baseline, alternative="greater").pvalue
        alpha = (
            0.025  # Bonferroni sufficient condition for both members of the Holm family
        )
        return "PASS" if improvement >= 0.05 and p < alpha else "FAIL"
    raise ValueError("Unknown historical PPO diagnostic")
