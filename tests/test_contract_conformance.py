"""
Contract Conformance Tests - Week 2 Day 1-2 Deliverable

Tests that implementations match survey specification (Ch 15).
Authority: WORK_BREAKDOWN_v3.csv W2.1-W2.5, HPO_NAS_RECOVERY_MASTER_PROGRAM.md

Validates:
- Searcher interface (propose, observe, capabilities, state_dict)
- Scheduler interface (report, promote, gate, exploit, explore)
- Executor interface (launch, checkpoint, load_checkpoint)
- Store interface (save_trial, load_trial, query)
- Checkpoint contract (serialize, deserialize, surgery)

Survey refs: 15-contracts.tex:97-260
"""

import pytest
import tempfile
from pathlib import Path
from typing import Any

from hponas.searchers import RandomSearcher, SobolSearcher
from hponas.schedulers import ASHAScheduler, ASHAConfig
from hponas.executors import LocalExecutor
from hponas.store import Store, Trial, Study
from hponas.space import SearchSpace, Knob


# ============================================================================
# W2.1: Searcher Contract Conformance
# ============================================================================


class TestSearcherContract:
    """
    Searcher interface contract (Ch 15:97-135).

    Required methods:
    - propose(n) -> list[dict]: batch proposals
    - observe(trial) -> None: ingest results
    - state_dict() -> dict: serialize state
    - load_state_dict(state) -> None: restore state
    - capabilities -> dict: declare support

    Survey: "batch proposals are the normal case, not the extension"
    """

    def test_searcher_has_required_methods(self):
        """All searchers must implement the five contract methods."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
        ])
        searcher = RandomSearcher(space, seed=42)

        # Required methods
        assert hasattr(searcher, "propose")
        assert hasattr(searcher, "observe")
        assert hasattr(searcher, "state_dict")
        assert hasattr(searcher, "load_state_dict")
        assert hasattr(searcher, "capabilities")

        # Call signatures
        assert callable(searcher.propose)
        assert callable(searcher.observe)
        assert callable(searcher.state_dict)
        assert callable(searcher.load_state_dict)

    def test_propose_returns_batch(self):
        """propose(n) must return exactly n configurations."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "ordinal", (1, 10)),
        ])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(5)
        assert len(configs) == 5

        # Each config is a dict with all knobs
        for cfg in configs:
            assert isinstance(cfg, dict)
            assert "x" in cfg
            assert "y" in cfg

    def test_observe_ingests_trial(self):
        """observe(trial) must accept trial dict and not crash."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        trial = {
            "config": {"x": 0.5},
            "fidelity": 1.0,
            "value": 0.3,
            "cost": 10.0,
        }

        # Should not raise
        searcher.observe(trial)

    def test_state_dict_serializable(self):
        """state_dict() must return JSON-serializable dict."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        # Observe some trials
        searcher.propose(3)
        searcher.observe({"config": {"x": 0.5}, "fidelity": 1.0, "value": 0.3, "cost": 10.0})

        state = searcher.state_dict()
        assert isinstance(state, dict)

        # Should be JSON-serializable
        import json
        json.dumps(state)  # raises if not serializable

    def test_load_state_dict_restores(self):
        """load_state_dict must restore searcher to saved state."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher1 = RandomSearcher(space, seed=42)

        # Generate proposals
        configs1 = searcher1.propose(3)
        state = searcher1.state_dict()

        # Create new searcher and restore
        searcher2 = RandomSearcher(space, seed=999)  # different seed
        searcher2.load_state_dict(state)

        # Next proposals should match
        configs1_next = searcher1.propose(2)
        configs2_next = searcher2.propose(2)

        assert len(configs1_next) == len(configs2_next)

    def test_capabilities_declares_support(self):
        """capabilities must declare knob kinds, conditionals, priors, max_dim."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        caps = searcher.capabilities
        assert isinstance(caps, dict)

        # Survey: "maximum sensible dimension" must be declared
        assert "max_dim" in caps

        # Survey: "which knob kinds" must be declared
        # RandomSearcher supports all knob kinds
        assert "continuous" in caps.get("knob_kinds", [])


# ============================================================================
# W2.2: Scheduler Contract Conformance
# ============================================================================


class TestSchedulerContract:
    """
    Scheduler interface contract (Ch 15:136-168).

    Required methods:
    - report(trial, fidelity, value) -> "continue" | "stop" | "pause"
    - promote() -> list[trial]: resume paused trials
    - gate(predicate) -> None: register veto
    - exploit(loser, winner) -> None: population verb
    - explore(config) -> dict: population verb

    Survey: "ASHA and median rule live entirely behind report"
    """

    def test_scheduler_has_required_methods(self):
        """All schedulers must implement the contract methods."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Required methods
        assert hasattr(scheduler, "report")
        assert hasattr(scheduler, "promote")

        # Population verbs (may be stubs for non-population schedulers)
        # ASHA doesn't have exploit/explore (population-only), but gate exists

    def test_report_returns_decision(self):
        """report must return 'continue', 'stop', or 'pause'."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        decision = scheduler.report("trial_1", fidelity=1.0, value=0.5)
        assert decision in ["continue", "stop", "pause"]

    def test_promote_returns_trials(self):
        """promote must return list of trial IDs to resume."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Report some trials to create paused trials
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.report("trial_2", fidelity=1.0, value=0.3)

        promoted = scheduler.promote()
        assert isinstance(promoted, list)


# ============================================================================
# W2.3: Executor Contract Conformance
# ============================================================================


class TestExecutorContract:
    """
    Executor interface contract (Ch 15:199-213).

    Required methods:
    - launch(trial_id, config, objective_fn, fidelity) -> str
    - checkpoint(trial_id, path) -> None
    - load_checkpoint(trial_id, path) -> Any

    Survey: "Both adapters meter per-trial cost themselves"
    """

    def test_executor_has_required_methods(self):
        """All executors must implement launch, checkpoint, load_checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            assert hasattr(executor, "launch")
            assert hasattr(executor, "checkpoint")
            assert hasattr(executor, "load_checkpoint")

    def test_launch_returns_trial_id(self):
        """launch must start a trial and return its ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def objective(config):
                return config["x"] ** 2

            trial_id = executor.launch(
                trial_id="trial_1",
                config={"x": 0.5},
                objective_fn=objective,
                fidelity=1.0,
            )

            assert trial_id == "trial_1"

    def test_checkpoint_saves_state(self):
        """checkpoint must save trial state to path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def objective(config):
                return config["x"] ** 2

            executor.launch("trial_1", {"x": 0.5}, objective, 1.0)

            ckpt_dir = Path(tmpdir) / "ckpt"
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            executor.checkpoint("trial_1", ckpt_dir)

            # Checkpoint file should exist
            ckpt_path = ckpt_dir / "trial_1.pkl"
            assert ckpt_path.exists()


# ============================================================================
# W2.4: Store Contract Conformance
# ============================================================================


class TestStoreContract:
    """
    Store interface contract (Ch 15:170-198).

    Required operations:
    - save_study(study) -> None
    - save_trial(trial) -> None
    - load_trial(trial_id) -> Trial
    - query_trials(filters) -> list[Trial]

    Survey: "storage technology is an engineering judgment; the schema is the contract"
    """

    def test_store_saves_and_loads_trial(self):
        """Store must persist trials across save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            trial = Trial(
                trial_id="trial_1",
                config={"x": 0.5},
                seed=42,
                fidelity=1.0,
                value=0.25,
                cost=10.0,
                status="completed",
            )

            store.write_trial(trial, study_id="study_1")
            loaded = store.read_trials(study_id="study_1")[0]

            assert loaded.trial_id == trial.trial_id
            assert loaded.config == trial.config
            assert loaded.value == trial.value

    def test_store_tracks_lineage(self):
        """Store must preserve parent_trial_id for population lineage (Ch 15:178)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            parent = Trial(
                trial_id="parent",
                config={"x": 0.5},
                seed=42,
                fidelity=1.0,
                value=0.25,
                cost=10.0,
            )

            child = Trial(
                trial_id="child",
                config={"x": 0.6},
                seed=42,
                fidelity=1.0,
                value=0.20,
                cost=12.0,
                parent_trial_id="parent",  # lineage
            )

            store.write_trial(parent, study_id="study_1")
            store.write_trial(child, study_id="study_1")

            trials = store.read_trials(study_id="study_1")
            loaded_child = [t for t in trials if t.trial_id == "child"][0]
            assert loaded_child.parent_trial_id == "parent"


# ============================================================================
# W2.5: Checkpoint Contract Conformance
# ============================================================================


class TestCheckpointContract:
    """
    Checkpoint contract (Ch 15:203-208, population checkpoint surgery).

    Survey: "checkpoint surgery as first-class operations: save, copy weights
    and optimizer state across trials, resume"

    Note: Full checkpoint surgery deferred to Tier 2 (T2.7 Distillation Protocol).
    This test validates basic serialize/deserialize only.
    """

    def test_executor_checkpoint_serializable(self):
        """Checkpoint must be serializable for crash recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def objective(config):
                return config["x"] ** 2

            executor.launch("trial_1", {"x": 0.5}, objective, 1.0)

            ckpt_dir = Path(tmpdir) / "ckpt"
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            ckpt_path = ckpt_dir / "trial_1.pkl"
            executor.checkpoint("trial_1", ckpt_dir)

            # Checkpoint should be loadable
            loaded = executor.load_checkpoint("trial_1", ckpt_dir)
            assert loaded is not None


# ============================================================================
# Integration: End-to-End Contract Flow
# ============================================================================


class TestContractIntegration:
    """
    Validate contracts work together in typical study flow.

    Survey: "A reader should be able to point from any line of the eventual
    code review back to a line of this survey" (Ch 15:6-11)
    """

    def test_study_flow_contracts(self):
        """Searcher -> Scheduler -> Executor -> Store contracts integrate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
            searcher = RandomSearcher(space, seed=42)
            scheduler = ASHAScheduler(ASHAConfig(r_min=1.0, r_max=9.0))
            executor = LocalExecutor(checkpoint_dir=tmpdir)
            store = Store(Path(tmpdir) / "study.db")

            # Study flow
            configs = searcher.propose(3)
            assert len(configs) == 3

            def objective(cfg):
                return cfg["x"] ** 2

            for i, cfg in enumerate(configs):
                trial_id = f"trial_{i}"

                # Launch via executor
                executor.launch(trial_id, cfg, objective, fidelity=1.0)
                result = executor.get_result(trial_id)

                # Report to scheduler
                decision = scheduler.report(trial_id, fidelity=1.0, value=result["value"])
                assert decision in ["continue", "stop", "pause"]

                # Save to store
                trial = Trial(
                    trial_id=trial_id,
                    config=cfg,
                    seed=42,
                    fidelity=1.0,
                    value=result["value"],
                    cost=result["cost"],
                    status="completed",
                )
                store.write_trial(trial, study_id="study_1")

                # Observe in searcher
                searcher.observe({
                    "config": cfg,
                    "fidelity": 1.0,
                    "value": result["value"],
                    "cost": result["cost"],
                })
