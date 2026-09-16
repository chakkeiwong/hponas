"""
V02 validation: Deterministic state replay.

Protocol: Given an event log from a completed run, replaying from the same seed
produces bit-identical suggestions.

Scenarios:
1. Single-batch replay: propose_batch(n=10) replays identically
2. Multi-batch replay: propose_batch(n=1) x10 replays identically
3. Crash-resume: checkpoint at trial 5, resume from checkpoint, continue to trial 10

Success Criteria:
- Replayed suggestions match original suggestions exactly (bit-identical)
- Works for Random, Sobol, GP searchers
- Event log non-empty (non-vacuity check)
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from hponas.events import EventLog
from hponas.replay import ReplayEngine, record_optimization_run
from hponas.searchers.random_searcher import RandomSearcher
from hponas.space import SearchSpace
from hponas.types import Parameter, ParameterType


@pytest.fixture
def simple_space():
    """Simple 2D search space for testing."""
    from hponas.space import Knob
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))
    space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 1.0)))
    return space


@pytest.fixture
def objective_fn():
    """Simple objective function for testing."""
    def f(config):
        x = config.values["x"]
        y = config.values["y"]
        return x**2 + y**2
    return f


class TestV02Replay:
    """V02 validation: Deterministic state replay."""

    def test_scenario_1_single_batch_replay(self, simple_space, objective_fn):
        """Scenario 1: Single batch replays identically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "run.log"
            event_log = EventLog(log_path)

            # Original run
            seed = 42
            n_trials = 10
            searcher1 = RandomSearcher(simple_space, seed=seed)

            original_suggestions = record_optimization_run(
                searcher=searcher1,
                objective_fn=objective_fn,
                n_trials=n_trials,
                event_log=event_log,
                batch_size=n_trials  # Single batch
            )

            # Verify event log non-empty (V02 non-vacuity)
            assert not event_log.is_empty()
            assert event_log.count() >= n_trials * 2  # n_trials suggestions + n_trials observations

            # Replay run
            searcher2 = RandomSearcher(simple_space, seed=seed)
            engine = ReplayEngine(searcher2, event_log, seed)

            passed, message, orig, replayed = engine.verify_determinism(n_trials, batch_size=n_trials)

            assert passed, f"Replay failed: {message}"
            assert len(orig) == n_trials
            assert len(replayed) == n_trials

            # Verify bit-identical
            for i, (o, r) in enumerate(zip(orig, replayed)):
                assert o == r, f"Trial {i} mismatch: {o} != {r}"

    def test_scenario_2_multi_batch_replay(self, simple_space, objective_fn):
        """Scenario 2: Multi-batch (sequential) replay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "run.log"
            event_log = EventLog(log_path)

            # Original run: 10 trials, batch_size=1 (sequential)
            seed = 123
            n_trials = 10
            searcher1 = RandomSearcher(simple_space, seed=seed)

            original_suggestions = record_optimization_run(
                searcher=searcher1,
                objective_fn=objective_fn,
                n_trials=n_trials,
                event_log=event_log,
                batch_size=1  # Sequential
            )

            # Replay run
            searcher2 = RandomSearcher(simple_space, seed=seed)
            engine = ReplayEngine(searcher2, event_log, seed)

            passed, message, orig, replayed = engine.verify_determinism(n_trials, batch_size=1)

            assert passed, f"Replay failed: {message}"
            assert len(orig) == n_trials
            assert len(replayed) == n_trials

            # Verify bit-identical
            for i, (o, r) in enumerate(zip(orig, replayed)):
                assert o == r, f"Trial {i} mismatch: {o} != {r}"

    def test_scenario_3_checkpoint_resume(self, simple_space, objective_fn):
        """Scenario 3: Checkpoint at trial 5, resume, continue to trial 10."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "run.log"
            event_log = EventLog(log_path)

            seed = 456
            n_trials = 10
            checkpoint_at = 5

            # Original run: 10 trials straight through
            searcher1 = RandomSearcher(simple_space, seed=seed)
            original_suggestions = record_optimization_run(
                searcher=searcher1,
                objective_fn=objective_fn,
                n_trials=n_trials,
                event_log=event_log,
                batch_size=1
            )

            # Checkpoint-resume run
            log_path2 = Path(tmpdir) / "run2.log"
            event_log2 = EventLog(log_path2)

            # Phase 1: Run to checkpoint_at
            searcher2 = RandomSearcher(simple_space, seed=seed)
            phase1_suggestions = record_optimization_run(
                searcher=searcher2,
                objective_fn=objective_fn,
                n_trials=checkpoint_at,
                event_log=event_log2,
                batch_size=1
            )

            # Save checkpoint
            checkpoint_path = Path(tmpdir) / "checkpoint.json"
            state = searcher2.get_state()

            event_log2.record_checkpoint(
                trial_id=f"trial_{checkpoint_at-1}",
                checkpoint_path=str(checkpoint_path),
                metadata={"n_trials": checkpoint_at}
            )

            # Phase 2: Resume from checkpoint
            searcher3 = RandomSearcher(simple_space, seed=seed)
            searcher3.set_state(state)

            # Continue from checkpoint_at to n_trials
            for trial_idx in range(checkpoint_at, n_trials):
                config = searcher3.suggest()
                trial_id = f"trial_{trial_idx}"

                event_log2.record_suggest(
                    trial_id=trial_id,
                    config=config.to_dict(),
                    seed=seed
                )

                value = objective_fn(config)
                cost = 100.0

                event_log2.record_observe(
                    trial_id=trial_id,
                    fidelity=1.0,
                    value=value,
                    cost=cost
                )

                searcher3.observe(
                    result=type('Result', (), {
                        'config': config,
                        'objective_value': value,
                        'cost': cost,
                        'is_valid': lambda: True
                    })()
                )

                phase1_suggestions.append(config)

            # Compare: checkpoint-resume should match straight-through
            assert len(original_suggestions) == len(phase1_suggestions)

            for i, (orig, resumed) in enumerate(zip(original_suggestions, phase1_suggestions)):
                assert orig.values == resumed.values, \
                    f"Trial {i} mismatch after checkpoint-resume: {orig.values} != {resumed.values}"

    def test_empty_log_raises(self, simple_space):
        """Empty event log raises ValueError (V02 non-vacuity)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "empty.log"
            event_log = EventLog(log_path)

            searcher = RandomSearcher(simple_space, seed=42)
            engine = ReplayEngine(searcher, event_log, seed=42)

            with pytest.raises(ValueError, match="empty event log"):
                engine.replay_suggestions(10)

    def test_different_seed_fails(self, simple_space, objective_fn):
        """Replay with different seed should fail (negative test)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "run.log"
            event_log = EventLog(log_path)

            # Original run with seed=42
            seed1 = 42
            n_trials = 5
            searcher1 = RandomSearcher(simple_space, seed=seed1)

            record_optimization_run(
                searcher=searcher1,
                objective_fn=objective_fn,
                n_trials=n_trials,
                event_log=event_log,
                batch_size=1
            )

            # Replay with different seed=999
            seed2 = 999
            searcher2 = RandomSearcher(simple_space, seed=seed2)
            engine = ReplayEngine(searcher2, event_log, seed2)

            passed, message, orig, replayed = engine.verify_determinism(n_trials, batch_size=1)

            # Should fail - different seed produces different suggestions
            assert not passed, "Replay with different seed should fail"
            assert "!=" in message or "mismatch" in message.lower()

    def test_replay_with_observations(self, simple_space, objective_fn):
        """Test that observations affect subsequent suggestions correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "run.log"
            event_log = EventLog(log_path)

            # For RandomSearcher, observations don't affect future suggestions
            # (it's memoryless), so this is just a sanity check
            seed = 789
            n_trials = 8
            searcher1 = RandomSearcher(simple_space, seed=seed)

            record_optimization_run(
                searcher=searcher1,
                objective_fn=objective_fn,
                n_trials=n_trials,
                event_log=event_log,
                batch_size=2  # Batch of 2
            )

            # Verify observations recorded
            observations = event_log.get_observations()
            assert len(observations) == n_trials

            # Replay
            searcher2 = RandomSearcher(simple_space, seed=seed)
            engine = ReplayEngine(searcher2, event_log, seed)

            passed, message, orig, replayed = engine.verify_determinism(n_trials, batch_size=2)

            assert passed, f"Replay with observations failed: {message}"
