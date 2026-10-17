"""Analysis fixtures establish mechanics, never empirical performance or power."""

import copy
import hashlib
import json

import numpy as np
import pytest

from validation.evidence import decision
from validation.tier0_analysis import analyze, collect_blocks, endpoints, training_seed
from validation.tier0_campaign import make_arm, run_study, campaign, verify_arm_trace
from validation.tier0_design import (
    ACCOUNTING, ARMS, canonical_digest, design_errors, load_design, require_campaign_ready, study_stream_slot,
)
from validation.tier0_sizing import joint_bootstrap, pilot_model, size_joint_entry


@pytest.fixture
def design(tmp_path):
    d = load_design("validation/designs/tier0_candidate_v1.json")
    artifact = tmp_path / "fixture.json"
    artifact.write_text('{"engineering_fixture":true}')
    ids = list(d["tasks"])[:2]
    d["tasks"] = {tid: d["tasks"][tid] for tid in ids}
    d["entry_tasks"] = {entry: ids for entry in ARMS}
    d["seed_sets"] = {phase: seeds[:5] for phase, seeds in d["seed_sets"].items()}
    d["budget_grid"] = [0, 0.5, 1]
    d["margins"]["V04-T0"]["regret_auc"] = 0.0
    d["planning_effects"] = {entry: {endpoint: 0.1 for endpoint in endpoints}
                              for entry, endpoints in d["endpoints"].items()}
    d["resource"].update(owner="fixture", allocation_id="fixture-no-compute", campaign_cap_seconds=10000)
    d["dependencies"] = {name: "fixture" for name in
                         ("numpy", "scipy", "torch", "botorch", "gpytorch", "optuna", "jax", "jaxlib", "brax")}
    for task in d["tasks"].values():
        assets = [{"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]
        task.update(independence_basis="Independent artificial fixture; no scientific inference",
                    version="fixture", data_sha256=canonical_digest(assets), data_artifacts=assets,
                    artifact={"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()},
                    scale_bounds={"low": 0.0, "high": 100.0, "direction": "maximize"},
                    regret_reference=100.0, initial_objective=0.0,
                    space=[{"name": "rate", "kind": "continuous", "bounds": [0.001, 1.0], "transform": "log"}],
                    budget={"seconds": 10.0, "max_overshoot_seconds": 2.0, "trial_limit": 10})
        task["initial_configs"] = {str(seed): [{"rate": x} for x in (0.001, 0.01, 0.1, 0.5, 1.0)]
                                   for seeds in d["seed_sets"].values() for seed in seeds}
    assert design_errors(d) == []
    return d


def observations(design, phase="confirmation"):
    records = []
    for entry, arms in ARMS.items():
        for tid in design["entry_tasks"][entry]:
            for seed in design["seed_sets"][phase]:
                slot = study_stream_slot(design, tid, seed)
                for arm in arms:
                    score = 80.0 if arm in {"gp_log", "tpe_log"} else 20.0
                    configs = design["tasks"][tid]["initial_configs"][str(seed)] + [{"rate": 0.2}]
                    records.append({"entry": entry, "task": tid, "seed": seed, "arm": arm, "phase": phase,
                                    "rng_stream_slot": slot,
                                    "design_digest": canonical_digest(design), "accounting": ACCOUNTING,
                                    "budget_seconds": 10.0, "elapsed_seconds": 10.0,
                                    "accounting_complete": True, "status": "complete",
                                    "observations": [{"index": i, "value": score, "completed_seconds": i + 1.0,
                                                      "config": config, "training_seed": training_seed(slot, i)}
                                                     for i, config in enumerate(configs)]})
    return records


def test_repository_candidate_exposes_missing_inputs_and_cannot_spend(tmp_path):
    d = load_design("validation/designs/tier0_candidate_v1.json")
    errors = design_errors(d)
    assert any("scale bounds" in e for e in errors)
    assert any("regret_auc" in e for e in errors)
    assert any("allocation" in e for e in errors)
    with pytest.raises(ValueError, match="Incomplete Tier 0 design"):
        campaign("V05", tmp_path, design_path="validation/designs/tier0_candidate_v1.json", phase="pilot")
    assert not list(tmp_path.iterdir())


def test_complete_engineering_fixture_still_requires_certification(design, tmp_path, monkeypatch):
    from validation import tier0_design

    # This historical protocol test owns its decision context. A later master
    # amendment closing D-PROTOCOL must not change the refusal being tested.
    program = tmp_path / 'docs/program/program.json'
    program.parent.mkdir(parents=True)
    program.write_text(json.dumps({'decisions': [
        {'id': 'D-T0-CLAIMS', 'status': 'accepted'},
        {'id': 'D-PROTOCOL', 'status': 'open'},
        {'id': 'D-PILOT-ORDER', 'status': 'accepted'},
    ]}))
    monkeypatch.setattr(tier0_design, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match="D-PROTOCOL"):
        require_campaign_ready(design, "pilot")


def test_certified_label_cannot_reenable_invalidated_analysis(design):
    design['status'] = 'certified'
    with pytest.raises(ValueError, match='invalidated'):
        analyze(design, [])


def test_accepted_program_decisions_do_not_reenable_invalidated_campaign(design, tmp_path, monkeypatch):
    from validation import tier0_design

    program = tmp_path / 'docs/program/program.json'
    program.parent.mkdir(parents=True)
    program.write_text(json.dumps({'decisions': [
        {'id': key, 'status': 'accepted'} for key in ('D-T0-CLAIMS', 'D-PROTOCOL', 'D-PILOT-ORDER')
    ]}))
    monkeypatch.setattr(tier0_design, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='invalidated'):
        require_campaign_ready(design, 'pilot')


def test_evaluation_seed_namespaces_do_not_reuse_training_or_search_seeds(design):
    namespaces = []
    for seeds in design["seed_sets"].values():
        for seed in seeds:
            training = {training_seed(seed, i) for i in range(50)}
            search = {s + 100000 for s in training}
            assert not training & search
            namespaces.append(training | search)
    assert sum(map(len, namespaces)) == len(set.union(*namespaces))
    assert max(set.union(*namespaces)) < 2**32


def test_task_phase_block_namespaces_are_disjoint_and_frozen():
    d = load_design("validation/designs/tier0_candidate_v1.json")
    slots = [study_stream_slot(d, tid, seed) for tid in d["tasks"]
             for seeds in d["seed_sets"].values() for seed in seeds]
    assert len(slots) == len(set(slots)) == 135
    namespaces = [{training_seed(slot, i) + offset for i in range(50) for offset in (0, 100000)}
                  for slot in slots]
    assert len(set.union(*namespaces)) == sum(map(len, namespaces)) == 13500
    assert max(set.union(*namespaces)) < 2**32
    # Task index is explicitly frozen: dictionary ordering cannot reassign it.
    reverse = copy.deepcopy(d)
    reverse["tasks"] = dict(reversed(list(reverse["tasks"].items())))
    for tid in d["tasks"]:
        assert study_stream_slot(d, tid, 20000) == study_stream_slot(reverse, tid, 20000)


@pytest.mark.parametrize("fault", ["duplicate_index", "overlapping_seed", "overflow", "missing_policy"])
def test_stream_collisions_and_undefined_policies_refuse_design(design, fault):
    tasks = list(design["tasks"].values())
    if fault == "duplicate_index":
        tasks[1]["stream_task_index"] = tasks[0]["stream_task_index"]
    elif fault == "overlapping_seed":
        design["seed_sets"]["pilot"][-1] = design["seed_sets"]["pilot"][0] + 20
    elif fault == "overflow":
        tasks[1]["stream_task_index"] = 2000
    else:
        design.pop("random_stream_policy")
    assert any("stream" in error.lower() for error in design_errors(design))


def test_replay_rejects_a_wrong_task_stream_and_old_training_seed(design):
    tid = list(design["tasks"])[1]
    record = next(r for r in observations(design) if r["task"] == tid)
    forged = copy.deepcopy(record)
    forged["rng_stream_slot"] = forged["seed"]
    with pytest.raises(ValueError, match="random stream"):
        endpoints(design, tid, forged)
    with pytest.raises(ValueError, match="random stream"):
        verify_arm_trace(design, forged)
    record["observations"][0]["training_seed"] = training_seed(record["seed"], 0)
    with pytest.raises(ValueError, match="Evaluation seed"):
        endpoints(design, tid, record)


def test_study_factory_and_objective_use_the_same_task_namespace(design):
    seed = design["seed_sets"]["pilot"][0]
    proposals = []
    for tid in design["tasks"]:
        elapsed, seen = [0.0], []

        def objective(config, actual_seed, index):
            elapsed[0] += 2
            seen.append(actual_seed)
            return {"value": config["rate"]}

        record = run_study(design, "V04-T0", tid, seed, "random_log", "pilot", objective, clock=lambda: elapsed[0])
        slot = study_stream_slot(design, tid, seed)
        assert record["rng_stream_slot"] == slot
        assert seen == [training_seed(slot, i) for i in range(5)]
        assert verify_arm_trace(design, record)
        assert endpoints(design, tid, record) is not None
        proposals.append(record["observations"][0]["config"])
    assert proposals[0] != proposals[1]


@pytest.mark.parametrize("mutation", [
    lambda d: d["seed_sets"]["confirmation"].append(10000),
    lambda d: d["seed_sets"]["pilot"].append(10000),
    lambda d: d["margins"]["V04-T0"].pop("regret_auc"),
    lambda d: d["arms"]["V05"].__setitem__(1, "random_log"),
    lambda d: d["endpoints"]["V04-T0"].remove("regret_auc"),
    lambda d: next(iter(d["tasks"].values()))["scale_bounds"].__setitem__("high", float("inf")),
    lambda d: next(iter(d["tasks"].values()))["initial_configs"].clear(),
])
def test_incomplete_or_changed_design_fails_before_analysis(design, mutation):
    mutation(design)
    assert design_errors(design)
    with pytest.raises(ValueError):
        analyze(design, [])


def test_endpoints_hold_past_values_without_future_leakage_or_overshoot(design):
    record = observations(design)[0]
    record["elapsed_seconds"] = 11.0
    record["observations"][-1].update(completed_seconds=11.0, value=10000)
    result = endpoints(design, record["task"], record)
    assert result == pytest.approx({"final_objective": 80.0, "regret_auc": 0.6})
    record["elapsed_seconds"] = 12.001
    assert endpoints(design, record["task"], record) is None
    record["elapsed_seconds"] = 11
    record["accounting_complete"] = False
    assert endpoints(design, record["task"], record) is None


def test_joint_entry_all_methods_comparators_and_auc_are_required(design):
    raw = observations(design)
    result = analyze(design, raw)
    assert all(e["candidate_clears"] for e in result["entries"].values())
    assert len(result["entries"]["V04-T0"]["components"]) == 8
    for record in raw:
        if record["entry"] == "V04-T0" and record["arm"] == "tpe_log":
            for observation in record["observations"]:
                observation["value"] = 0 if observation["index"] < 5 else 100
    result = analyze(design, raw)
    # Final objective improves, but poor anytime quality vetoes the entry.
    assert not result["entries"]["V04-T0"]["candidate_clears"]
    assert result["entries"]["V04-T0"]["verdict"] == "INCONCLUSIVE"
    assert result["entries"]["V05"]["candidate_clears"]
    assert not result["certifies_acceptance"]


def test_isolated_entry_keeps_family_denominator_two(design):
    result = analyze(design, [r for r in observations(design) if r["entry"] == "V05"], entry_ids=["V05"])
    assert result["entries"]["V05"]["family"]["adjusted_alpha"] == 0.025


def test_missingness_counts_arms_and_excludes_complete_multiarm_block(design):
    raw = [r for r in observations(design) if r["entry"] == "V04-T0"]
    raw.pop(0)
    blocks, missing = collect_blocks(design, raw, "confirmation", "V04-T0")
    assert sum(len(rows) for rows in blocks.values()) == 9
    assert missing["missing_per_arm"]["gp_log"] == 1
    assert not missing["void"]  # Exactly 10%, not above 10%.
    raw.pop(3)
    _, missing = collect_blocks(design, raw, "confirmation", "V04-T0")
    assert missing["void"]


def test_missingness_union_is_not_mistaken_for_per_arm_loss(design):
    raw = [r for r in observations(design) if r["entry"] == "V04-T0"]
    removed = {id(raw[0]), id(raw[5])}  # Different blocks, different arms.
    raw = [r for r in raw if id(r) not in removed]
    blocks, missing = collect_blocks(design, raw, "confirmation", "V04-T0")
    assert sum(len(rows) for rows in blocks.values()) == 8
    assert not missing["void"]


@pytest.mark.parametrize("bad", ["duplicate", "seed", "phase", "time", "nan", "init"])
def test_forged_or_inconsistent_raw_evidence_is_rejected(design, bad):
    raw = observations(design)
    item = next(r for r in raw if r["entry"] == "V05")
    if bad == "duplicate":
        raw.append(copy.deepcopy(item))
    elif bad == "seed":
        item["seed"] = 999
    elif bad == "phase":
        item["phase"] = "pilot"
    elif bad == "time":
        item["observations"][1]["completed_seconds"] = 0.5
    elif bad == "nan":
        item["observations"][0]["value"] = float("nan")
    else:
        item["observations"][0]["config"]["rate"] = 0.002
    with pytest.raises(ValueError):
        analyze(design, raw)


def test_v05_factory_varies_only_encoding_and_starts_with_same_physical_design(design):
    tid = next(iter(design["tasks"]))
    seed = design["seed_sets"]["pilot"][0]
    configs = []
    for arm in ARMS["V05"]:
        time = [0.0]

        def objective(config, seed, index):
            time[0] += 2.0
            return {"value": config["rate"]}

        record = run_study(design, "V05", tid, seed, arm, "pilot", objective, clock=lambda: time[0])
        assert record["elapsed_seconds"] == 10
        assert record["status"] == "complete"
        configs.append([o["config"] for o in record["observations"]])
    assert configs[0] == configs[1] == design["tasks"][tid]["initial_configs"][str(seed)]
    log, linear = [make_arm(design, tid, arm, seed) for arm in ARMS["V05"]]
    from hponas import Config
    config = Config({"rate": 0.1})
    assert log._config_to_tensor(config).item() == pytest.approx(2 / 3)
    assert linear._config_to_tensor(config).item() == pytest.approx(0.099 / 0.999)
    assert log.num_restarts == linear.num_restarts == 10


def test_failure_or_trial_limit_is_missing_without_replacement(design):
    tid = next(iter(design["tasks"]))
    seed = design["seed_sets"]["pilot"][0]

    def failed(*unused):
        raise RuntimeError("fixture failure")

    result = run_study(design, "V04-T0", tid, seed, "random_log", "pilot", failed)
    assert result["status"] == "failed"
    assert result["seed"] == seed


def test_v05_enters_real_gp_acquisition_after_shared_initialization(design, monkeypatch):
    from hponas import GPSearcher

    monkeypatch.setattr(GPSearcher, "_sample_random", lambda self: pytest.fail("Unpaired GP random fallback"))
    tid = next(iter(design["tasks"]))
    seed = design["seed_sets"]["pilot"][0]
    records = []
    for arm in ARMS["V05"]:
        elapsed = [0.0]

        def objective(config, seed, index):
            elapsed[0] += 1.5
            return {"value": -(np.log10(config["rate"]) + 1.7) ** 2}

        record = run_study(design, "V05", tid, seed, arm, "pilot", objective, clock=lambda: elapsed[0])
        assert record["status"] == "complete", record.get("failure")
        assert len(record["observations"]) == 7
        assert endpoints(design, tid, record) is not None
        assert verify_arm_trace(design, record)
        records.append(record)
    assert [r["config"] for r in records[0]["observations"][:5]] == [r["config"] for r in records[1]["observations"][:5]]
    records[0]["arm"] = "gp_linear"
    with pytest.raises(ValueError, match="Method label"):
        verify_arm_trace(design, records[0])


def test_all_registered_arm_factories_run_their_actual_searchers(design):
    tid = next(iter(design["tasks"]))
    seed = design["seed_sets"]["pilot"][0]
    from hponas import Result
    from hponas.searchers.adapter import LegacySearcherAdapter

    for arm in ARMS["V04-T0"]:
        target = make_arm(design, tid, arm, seed)
        assert isinstance(target, LegacySearcherAdapter) == (arm == "tpe_log")
        # Reach TPE's adaptive phase, not just its initial uniform sampler.
        for index in range(12 if arm == "tpe_log" else 6):
            config = target.suggest()
            target.trials[str(index)] = config
            target.observe(Result(str(index), -config["rate"] ** 2))
        assert len(target.history) == (12 if arm == "tpe_log" else 6)


def test_statistics_refuse_duplicate_nonfinite_and_invalid_family_inputs():
    from validation.stats import PairedBlock, ScaleBounds, build_clusters, holm_bonferroni

    bounds = {"a": ScaleBounds(0, 1)}
    row = PairedBlock("a", 1, 0.0, 1.0)
    with pytest.raises(ValueError, match="Duplicate"):
        build_clusters([row, row], bounds)
    with pytest.raises(ValueError, match="Nonfinite"):
        build_clusters([PairedBlock("a", 1, float("nan"), 1.0)], bounds)
    with pytest.raises(ValueError):
        ScaleBounds(0, float("inf"))
    with pytest.raises(ValueError):
        holm_bonferroni({"V05": float("nan")})


def test_legacy_evidence_can_never_certify_registered_comparisons():
    for entry in ARMS:
        assert decision(entry, {"schema_version": 1, "validation_id": entry,
                                "passed": True, "real_workload": True, "workload": "brax_ppo"}) == "INCONCLUSIVE"


def test_joint_bootstrap_retains_component_correlation_and_sizing_is_reproducible():
    values = np.arange(10.0).reshape(2, 5)
    samples = np.stack([values, -values], axis=-1)
    boot = joint_bootstrap(samples, 100, np.random.default_rng(4))
    np.testing.assert_allclose(boot[:, 0], -boot[:, 1])
    blocks = {"a": samples[0] / 100, "b": samples[1] / 100}
    a = size_joint_entry(blocks, [0.4, 0.4], [0.0, 0.0], candidates=[5], replicates=8, draws=99)
    assert a == size_joint_entry(blocks, [0.4, 0.4], [0.0, 0.0], candidates=[5], replicates=8, draws=99)
    assert a["engineering_fixture"]
    assert len(a["curve"][0]["one_sided_component_coverage"]) == 2
    with pytest.raises(ValueError, match="five"):
        pilot_model({"a": samples[0][:3], "b": samples[1]})
    with pytest.raises(ValueError, match="cap"):
        size_joint_entry(blocks, [0.4, 0.4], [0.0, 0.0], candidates=[21], replicates=8, draws=99)
