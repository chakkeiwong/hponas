"""Exercise the installed wheel from outside the checkout.

This is installation evidence, not a scientific acceptance campaign. Run in a
fresh venv with ``python -m tools.check_installed --output receipt.json``.
"""

from __future__ import annotations

import argparse
from importlib import metadata, resources
import json
from pathlib import Path
import sys
import tempfile


def verify(extras=False, ray=False, rl=False):
    import hponas
    from hponas import GPSearcher, Knob, LocalExecutor, RandomSearcher, SearchSpace, Study
    from hponas.schedulers import ASHAConfig, ASHAScheduler, PASHAConfig, PASHAScheduler
    from hponas.store import Store

    origin = Path(hponas.__file__).resolve()
    if not origin.is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError(f"Expected installed wheel in this venv, got {origin}")
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("Installation verification requires an isolated venv")
    protocols = resources.files("validation").joinpath("protocols.json")
    entries = json.loads(protocols.read_text())["entries"]
    assert set(entries) == {'V01','V02','V03','V04-T0','V04-T1','V05','V06','V07','V08',
                            'V09','V10','V11a','V11b','V12','V13','V14','V15a','V15b','V16','V-COST'}
    assert resources.files("validation").joinpath("protocols/v03_protocol.md").is_file()
    space = SearchSpace([Knob("x", "continuous", (0., 1.)), Knob("y", "continuous", (1e-4, 1e-1), transform="log")])

    def objective(config):
        return (config["x"] - .25)**2 + config["y"]

    checks = {}
    with tempfile.TemporaryDirectory(prefix="hponas-installed-") as directory:
        from validation.evidence import AuditContextError
        from validation.run_validation_with_audit import ValidationRunner

        rejected_output = Path(directory) / "audited"
        try:
            ValidationRunner("V14", artifact_root=rejected_output)
        except AuditContextError as exc:
            assert "full HPO-NAS Git checkout" in str(exc)
        else:
            raise AssertionError("Installed wheel must not claim repository provenance")
        assert not rejected_output.exists()
        checks["audited_campaign_requires_checkout"] = True
        store = Store(Path(directory) / "study.db")
        calls = []

        def interrupt(config):
            calls.append(config)
            if len(calls) == 4:
                raise KeyboardInterrupt("installation checkpoint probe")
            return objective(config)

        try:
            study = Study(GPSearcher(space, seed=42, initial_random_samples=3, num_restarts=2),
                          LocalExecutor(), interrupt, budget=7, maximize=False,
                          store=store, study_name="installed")
            try:
                study.run()
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("Interruption was not exercised")
            committed = dict(study.results)
            resumed = Study(GPSearcher(space), LocalExecutor(), objective,
                            store=store, study_name="installed")
            resumed.load_checkpoint()
            result = resumed.run()
            assert result.n_trials == 7 and len(resumed.trials) == 7
            assert all(resumed.results[k] == v for k, v in committed.items())
            assert result.best_value == min(r.objective_value for r in result.history)
            checks["gp_store_resume"] = {"trials": result.n_trials, "committed_preserved": len(committed)}
        finally:
            store.close()
        pasha = PASHAScheduler(PASHAConfig(r_min=1, r_max=27))
        result = Study(RandomSearcher(space, seed=3), LocalExecutor(), objective,
                       budget=6, maximize=False, scheduler=pasha).run()
        assert {r.fidelity for r in result.history} == {1, 3}
        checks["pasha_stable_cap"] = pasha.current_max_fidelity
        def streamed(config, fidelity, resume_from, checkpoint, reporter):
            if resume_from:
                assert checkpoint == {"step": resume_from}
            for step in range(int(resume_from) + 1, int(fidelity) + 1):
                reporter(step, 1., cost=step - resume_from, checkpoint={"step": step})
            return {"value": 1., "cost": fidelity - resume_from}

        streaming_study = Study(
            RandomSearcher(space, seed=3), LocalExecutor(mode="async", max_workers=2), streamed,
            budget=2, scheduler=ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=2)),
            continuation="resume", checkpoint_dir=directory, study_name="streamed",
        )
        streamed_result = streaming_study.run()
        assert streamed_result.total_cost == 4 and streamed_result.n_trials == 4
        assert set(streaming_study.scheduler._terminal.values()) == {"completed"}
        checks["asha_streamed_resume"] = {"cost": streamed_result.total_cost, "evaluations": streamed_result.n_trials}
        from hponas import IncompleteStudyError
        underfilled = Study(RandomSearcher(space, seed=3), LocalExecutor(), objective,
                            budget=1, scheduler=ASHAScheduler(ASHAConfig(r_min=1, r_max=3)))
        try:
            underfilled.run()
        except IncompleteStudyError as exc:
            assert exc.result.best_config is None and len(exc.result.history) == 1
        else:
            raise AssertionError("Underfilled ASHA cannot claim a full-fidelity incumbent")
        checks["asha_explicit_incomplete"] = True
        if extras:
            from hponas import CMAESSearcher
            from hponas.searchers_tpe import TPESearcher

            for name, searcher in [("cmaes", CMAESSearcher(space, seed=3)), ("tpe", TPESearcher(space, seed=3))]:
                result = Study(searcher, LocalExecutor(), objective, budget=16, maximize=False).run()
                assert result.n_trials == 16 and all(r.is_valid() for r in result.history)
                checks[name] = result.n_trials
        if ray:
            from hponas import RayExecutor

            result = Study(RandomSearcher(space, seed=2), RayExecutor(num_workers=2),
                           objective, budget=4, maximize=False, max_concurrent=2).run()
            assert result.n_trials == 4 and all(r.is_valid() for r in result.history)
            checks["local_ray"] = result.n_trials
            result = Study(RandomSearcher(space, seed=2), RayExecutor(num_workers=1, max_retries=0),
                           streamed, budget=2, continuation="resume",
                           scheduler=ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=2))).run()
            assert result.total_cost == 4 and result.n_trials == 4
            checks["ray_streamed_resume"] = result.total_cost
        if rl:
            from workloads.rl_routine import RLSettings, rl_routine, evaluate_checkpoint

            trained = rl_routine({"width": 8, "depth": 1, "num_envs": 32, "batch_size": 64},
                                 seed=42, settings=RLSettings.smoke(),
                                 artifact_dir=Path(directory) / "policy", trial_id="installed-ppo")
            protected = evaluate_checkpoint(trained["artifacts"]["checkpoint"], 999)
            assert trained["metadata"]["training_seed"] == 42
            assert trained["metadata"]["search_seed"] != 999
            assert protected["value"] == protected["value"]
            checks["ppo_checkpoint_reload"] = {"search_value": trained["value"], "protected_value": protected["value"]}
    versions = {}
    for name in ["hponas", "numpy", "scipy", "torch", "gpytorch", "botorch", "optuna", "cmaes", "ray", "jax", "jaxlib", "brax"]:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return {"kind": "installation_verification", "scientific_acceptance": False,
            "python": sys.version, "prefix": sys.prefix, "base_prefix": sys.base_prefix,
            "installed_origin": str(origin), "checks": checks, "versions": versions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extras", action="store_true")
    parser.add_argument("--ray", action="store_true")
    parser.add_argument("--rl", action="store_true")
    options = parser.parse_args()
    receipt = verify(options.extras, options.ray, options.rl)
    options.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
