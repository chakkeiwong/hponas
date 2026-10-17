"""Compatibility APIs still used by workloads must retain state and checkpoints."""

import copy
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import qmc

import hponas.legacy_executors as executors
from hponas.legacy_searchers import RandomSearcher, SobolSearcher
from hponas.space import Knob, SearchSpace


def mixed_space(categorical_only=False):
    knobs = [Knob("choice", "categorical", ["left", "right", "center"])]
    if not categorical_only:
        knobs += [
            Knob("x", "continuous", (-3.0, 7.0)),
            Knob("rate", "continuous", (0.001, 1.0), transform="log"),
            Knob("depth", "ordinal", (2, 7)),
        ]
    return SearchSpace(knobs)


@pytest.mark.parametrize("cls", [RandomSearcher, SobolSearcher])
@pytest.mark.parametrize("count", [0, 1, 4, 7])
@pytest.mark.parametrize("categorical_only", [False, True])
def test_legacy_checkpoint_restarts_the_exact_mixed_sequence(
    cls, count, categorical_only
):
    space = mixed_space(categorical_only)
    original = cls(space, seed=0)
    original.propose(count)
    state = copy.deepcopy(original.state_dict())
    assert state["seed"] == 0 and state["n_proposed"] == count
    expected = original.propose(8)
    restored = cls(space, seed=123)
    restored.propose(3)
    restored.load_state_dict(state)
    assert restored.seed == 0
    assert restored.propose(8) == expected
    assert restored.state_dict()["n_proposed"] == count + 8


@pytest.mark.parametrize("field", ["cont_knobs", "ord_knobs", "cat_knobs"])
def test_sobol_rejects_each_changed_knob_group_before_changing_state(field):
    searcher = SobolSearcher(mixed_space(), seed=7)
    state = copy.deepcopy(searcher.state_dict())
    state[field] = ["different"]
    with pytest.raises(ValueError, match="does not match space"):
        searcher.load_state_dict(state)
    assert searcher.state_dict() == SobolSearcher(mixed_space(), seed=7).state_dict()


@pytest.mark.parametrize("workers", [1, 2])
def test_legacy_local_results_and_checkpoints_keep_envelope(
    tmp_path, monkeypatch, workers
):
    executor = executors.LocalExecutor(
        tmp_path / "nested" / "checkpoints", max_workers=workers
    )
    assert executor.max_workers == workers
    ticks = iter([10.0, 10.5])
    monkeypatch.setattr(executors.time, "time", lambda: next(ticks))
    try:
        assert executor.launch("trial", {"x": 3}, lambda c: c["x"] + 1, 2.0) == "trial"
        expected = {
            "config": {"x": 3},
            "value": 4,
            "cost": 0.5,
            "fidelity": 2.0,
            "status": "completed",
        }
        assert executor.get_result("trial") == expected
        assert executor.get_result("trial") == expected
        assert executor.get_result("missing") == {}
        executor.checkpoint("trial", tmp_path)
        assert executor.load_checkpoint("trial", tmp_path) == expected
        assert executor.load_checkpoint("absent", tmp_path) is None
        executor.checkpoint("absent", tmp_path)
        assert not (tmp_path / "absent.pkl").exists()
    finally:
        if executor._executor is not None:
            executor._executor.shutdown()


def test_legacy_local_failure_preserves_diagnostics_and_elapsed_cost(
    tmp_path, monkeypatch
):
    ticks = iter([10.0, 10.75])
    monkeypatch.setattr(executors.time, "time", lambda: next(ticks))
    executor = executors.LocalExecutor(tmp_path)

    def fail(config):
        raise ValueError("bad input")

    executor.launch("failed", {"x": 3}, fail, 4.0)
    assert executor.get_result("failed") == {
        "config": {"x": 3},
        "cost": 0.75,
        "fidelity": 4.0,
        "status": "failed",
        "error": "ValueError: bad input",
    }


class GetTimeoutError(Exception):
    pass


@pytest.fixture
def ray_transport(monkeypatch):
    real_wrapper = executors._run_trial_remote._function
    state = SimpleNamespace(
        initialized=False, inits=[], resources=[], cancelled=[], timeout=False
    )

    def init(**kwargs):
        state.inits.append(kwargs)
        state.initialized = True

    def get(result, timeout=None):
        state.last_timeout = timeout
        if state.timeout:
            raise GetTimeoutError()
        return result

    def options(**kwargs):
        state.resources.append(kwargs)
        return SimpleNamespace(remote=real_wrapper)

    monkeypatch.setattr(
        executors,
        "ray",
        SimpleNamespace(
            is_initialized=lambda: state.initialized,
            init=init,
            get=get,
            wait=lambda refs, timeout: ([], refs) if state.timeout else (refs, []),
            cancel=state.cancelled.append,
            exceptions=SimpleNamespace(GetTimeoutError=GetTimeoutError),
        ),
    )
    monkeypatch.setattr(
        executors, "_run_trial_remote", SimpleNamespace(options=options)
    )
    return state


def test_legacy_ray_checkpoint_roundtrip_and_copy_without_cluster(
    tmp_path, monkeypatch, ray_transport
):
    executor = executors.RayExecutor(
        tmp_path / "nested" / "source",
        num_cpus=2.0,
        num_gpus=0.5,
        ray_address="existing-address",
    )
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(executors.time, "time", lambda: next(ticks))
    assert executor.launch("trial", {"x": 3}, lambda c: c["x"] * 2, 4.0) == "trial"
    result = executor.poll("trial")
    assert result == {
        "trial_id": "trial",
        "value": 6,
        "cost": 0.25,
        "checkpoint_path": str(tmp_path / "nested/source/trial.pkl"),
        "status": "completed",
    }
    assert ray_transport.inits == [
        {"address": "existing-address", "ignore_reinit_error": True}
    ]
    assert ray_transport.resources == [{"num_cpus": 2.0, "num_gpus": 0.5}]
    target = tmp_path / "export"
    target.mkdir()
    executor.checkpoint("trial", target)
    checkpoint = {"config": {"x": 3}, "value": 6, "fidelity": 4.0, "cost": 0.25}
    assert executor.load_checkpoint("trial", target) == checkpoint
    executor.copy_checkpoint("trial", "clone")
    assert executor.load_checkpoint("clone", executor.checkpoint_dir) == checkpoint
    assert executor.load_checkpoint("missing", target) is None
    with pytest.raises(KeyError):
        executor.checkpoint("missing", target)
    with pytest.raises(FileNotFoundError):
        executor.copy_checkpoint("missing", "new")
    with pytest.raises(KeyError):
        executor.get_result("missing")
    ray_transport.timeout = True
    waiting = executor.get_result("trial", timeout=0.25)
    assert (
        waiting["trial_id"],
        waiting["value"],
        waiting["cost"],
        waiting["status"],
    ) == ("trial", None, 0.0, "running")
    assert waiting["error"] and ray_transport.last_timeout == 0.25
    executor.shutdown()
    assert ray_transport.cancelled == [result]
    assert executor._futures == {} and executor._trial_configs == {}


def test_legacy_ray_failed_objective_does_not_create_checkpoint(
    tmp_path, monkeypatch, ray_transport
):
    ray_transport.initialized = True
    executor = executors.RayExecutor(tmp_path)
    assert executor.num_cpus == 1.0 and executor.num_gpus == 0.0
    ticks = iter([20.0, 20.5])
    monkeypatch.setattr(executors.time, "time", lambda: next(ticks))

    def fail(config):
        raise ValueError("bad objective")

    executor.launch("failed", {}, fail, 4.0)
    assert executor.get_result("failed") == {
        "trial_id": "failed",
        "value": None,
        "cost": 0.5,
        "error": "bad objective",
        "status": "failed",
    }
    assert ray_transport.inits == []
    executor.checkpoint("failed", tmp_path)
    assert executor.load_checkpoint("failed", tmp_path) is None
    executor.shutdown()


def test_sobol_mixed_columns_match_independent_reference_and_defaults():
    space = mixed_space()
    space.knobs.append(Knob("width", "ordinal", (10, 20)))
    searcher = SobolSearcher(space)
    assert searcher.space is space and searcher.seed == 0
    points = qmc.Sobol(d=4, scramble=True, seed=0).random(8)
    categories = np.random.default_rng(0).choice(["left", "right", "center"], size=8)
    for config, point, category in zip(searcher.propose(8), points, categories):
        assert config["x"] == pytest.approx(-3 + 10 * point[0])
        assert config["rate"] == pytest.approx(10 ** (-3 + 3 * point[1]))
        assert config["depth"] == 2 + int(6 * point[2])
        assert config["width"] == 10 + int(11 * point[3])
        assert config["choice"] == category
    assert RandomSearcher(space).seed == 0


def test_random_recovery_preserves_rng_draws_with_large_integer_range():
    space = SearchSpace(
        [
            Knob("integer", "ordinal", (2**30, 2**32)),
            Knob("real", "continuous", (0.0, 1.0)),
        ]
    )
    original = RandomSearcher(space, seed=0)
    original.propose(64)
    restored = RandomSearcher(space, seed=0)
    restored.load_state_dict(original.state_dict())
    assert restored.propose(16) == original.propose(16)


def test_legacy_local_async_launch_returns_before_objective_and_preserves_pending_checkpoint(
    tmp_path,
):
    executor = executors.LocalExecutor(tmp_path, max_workers=2)
    release = threading.Event()
    began = [threading.Event() for _ in range(3)]

    def objective(config):
        began[config["index"]].set()
        assert release.wait(5.0)
        return config["index"]

    launcher = ThreadPoolExecutor(max_workers=1)
    try:
        submitted = launcher.submit(executor.launch, "a", {"index": 0}, objective, 4.0)
        assert submitted.result(timeout=1.0) == "a"
        executor.launch("b", {"index": 1}, objective, 4.0)
        executor.launch("c", {"index": 2}, objective, 4.0)
        assert began[0].wait(1.0) and began[1].wait(1.0)
        assert not began[2].wait(0.05)
        executor.checkpoint("a", tmp_path)
        assert executor.load_checkpoint("a", tmp_path) == {
            "config": {"index": 0},
            "fidelity": 4.0,
            "status": "running",
        }
    finally:
        release.set()
        launcher.shutdown()
        if executor._executor is not None:
            executor._executor.shutdown()


def test_missing_ray_dependency_has_clean_constructor_and_cleanup(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(executors, "RAY_AVAILABLE", False)
    executor = object.__new__(executors.RayExecutor)
    with pytest.raises(ImportError, match="requires ray"):
        executor.__init__(tmp_path)
    executor.__del__()


def test_legacy_local_default_runs_objective_on_the_calling_thread(tmp_path):
    executor = executors.LocalExecutor(tmp_path)
    try:
        executor.launch("sync", {}, lambda config: threading.get_ident(), 1.0)
        assert executor.get_result("sync")["value"] == threading.get_ident()
    finally:
        if executor._executor is not None:
            executor._executor.shutdown()
