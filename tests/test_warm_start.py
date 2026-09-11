"""
Test warm start: seed searchers from prior run-store trials.

Survey reference: Ch 8 sec:warm-start-from-store, validation V12.
Tier 1: implementation + unit tests (V12 campaign is Tier 2).
"""

import tempfile
from pathlib import Path

from hponas.legacy_searchers import SobolSearcher
from hponas.space import Knob, SearchSpace
from hponas.store import Store, Study, Trial
from hponas.warm_start import (
    WarmStartSearcher,
    check_space_compatibility,
    load_seed_configs,
    load_seed_configs_from_all_studies,
)


def test_load_seed_configs_compatible():
    """Load seeds from a study with compatible space."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        # Setup space
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))
        space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 1.0)))

        # Write study and trials
        store.write_study(Study(
            study_id="study_1",
            space_json=space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))

        store.write_trial(Trial(
            trial_id="trial_0",
            config={"x": 0.2, "y": 0.3},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        store.write_trial(Trial(
            trial_id="trial_1",
            config={"x": 0.8, "y": 0.9},
            seed=42,
            fidelity=1.0,
            value=0.1,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        # Load seeds
        seeds = load_seed_configs(store, "study_1", space, n=2, objective="minimize")

        assert len(seeds) == 2
        # Best first (minimize)
        assert seeds[0] == {"x": 0.8, "y": 0.9}
        assert seeds[1] == {"x": 0.2, "y": 0.3}

        store.close()


def test_load_seed_configs_incompatible():
    """Incompatible configs are skipped, not raised."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        # Source space: x, y
        source_space = SearchSpace()
        source_space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))
        source_space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 1.0)))

        store.write_study(Study(
            study_id="study_1",
            space_json=source_space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))

        store.write_trial(Trial(
            trial_id="trial_0",
            config={"x": 0.2, "y": 0.3},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        # Target space: x, z (different knob set)
        target_space = SearchSpace()
        target_space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))
        target_space.add_knob(Knob(name="z", kind="continuous", bounds=(0.0, 1.0)))

        seeds = load_seed_configs(store, "study_1", target_space, n=2, objective="minimize")

        # Config {"x": 0.2, "y": 0.3} fails validation (missing z, extra y) — skipped
        assert seeds == []

        store.close()


def test_load_seed_configs_nonexistent_study():
    """Nonexistent study returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        seeds = load_seed_configs(store, "nonexistent", space, n=10)

        assert seeds == []

        store.close()


def test_check_space_compatibility_matching():
    """Matching spaces are compatible."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))
    space.add_knob(Knob(name="y", kind="ordinal", bounds=(1, 10)))

    json_str = space.to_json()

    assert check_space_compatibility(json_str, space) is True


def test_check_space_compatibility_mismatched_knob_set():
    """Different knob names are incompatible."""
    space_a = SearchSpace()
    space_a.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    space_b = SearchSpace()
    space_b.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 1.0)))

    assert check_space_compatibility(space_a.to_json(), space_b) is False


def test_check_space_compatibility_mismatched_bounds():
    """Different bounds are incompatible."""
    space_a = SearchSpace()
    space_a.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    space_b = SearchSpace()
    space_b.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 10.0)))

    assert check_space_compatibility(space_a.to_json(), space_b) is False


def test_check_space_compatibility_legacy_unparseable():
    """Unparseable JSON is treated as incompatible, not raised."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    # Malformed JSON
    assert check_space_compatibility("{not json", space) is False

    # Legacy Python repr (pre-canonical-JSON stores)
    assert check_space_compatibility("[Knob(name='x', ...)]", space) is False


def test_load_seed_configs_from_all_studies():
    """Load seeds from multiple compatible studies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        # Study 1
        store.write_study(Study(
            study_id="study_1",
            space_json=space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))
        store.write_trial(Trial(
            trial_id="trial_1a",
            config={"x": 0.2},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        # Study 2
        store.write_study(Study(
            study_id="study_2",
            space_json=space.to_json(),
            objective="minimize",
            seed=99,
            budget=100.0,
        ))
        store.write_trial(Trial(
            trial_id="trial_2a",
            config={"x": 0.8},
            seed=99,
            fidelity=1.0,
            value=0.1,
            cost=1.0,
            status="completed",
        ), study_id="study_2")

        seeds = load_seed_configs_from_all_studies(store, space, n=2, objective="minimize")

        assert len(seeds) == 2
        # Best first across studies (0.1 < 0.5)
        assert seeds[0] == {"x": 0.8}
        assert seeds[1] == {"x": 0.2}

        store.close()


def test_load_seed_configs_from_all_studies_exclude():
    """Excluded studies are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        store.write_study(Study(
            study_id="study_1",
            space_json=space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))
        store.write_trial(Trial(
            trial_id="trial_1a",
            config={"x": 0.2},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        store.write_study(Study(
            study_id="study_2",
            space_json=space.to_json(),
            objective="minimize",
            seed=99,
            budget=100.0,
        ))
        store.write_trial(Trial(
            trial_id="trial_2a",
            config={"x": 0.8},
            seed=99,
            fidelity=1.0,
            value=0.1,
            cost=1.0,
            status="completed",
        ), study_id="study_2")

        seeds = load_seed_configs_from_all_studies(
            store, space, n=2, objective="minimize", exclude_study_ids=["study_2"]
        )

        # study_2 excluded, only study_1 trial remains
        assert len(seeds) == 1
        assert seeds[0] == {"x": 0.2}

        store.close()


def test_warm_start_searcher_propose_drains_seeds():
    """WarmStartSearcher proposes seeds before delegating to base."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    base = SobolSearcher(space, seed=42)
    seeds = [{"x": 0.1}, {"x": 0.2}, {"x": 0.3}]
    searcher = WarmStartSearcher(base, seeds)

    # First batch: all seeds
    batch1 = searcher.propose(2)
    assert len(batch1) == 2
    assert batch1[0] == {"x": 0.1}
    assert batch1[1] == {"x": 0.2}
    assert searcher.n_seeds_remaining == 1
    assert searcher.n_seeds_used == 2

    # Second batch: last seed + base searcher
    batch2 = searcher.propose(2)
    assert len(batch2) == 2
    assert batch2[0] == {"x": 0.3}
    # batch2[1] is from base (Sobol), value not checked
    assert searcher.n_seeds_remaining == 0
    assert searcher.n_seeds_used == 3

    # Third batch: all from base
    batch3 = searcher.propose(2)
    assert len(batch3) == 2
    assert searcher.n_seeds_remaining == 0
    assert searcher.n_seeds_used == 3


def test_warm_start_searcher_propose_n_zero():
    """propose(0) returns empty list."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    base = SobolSearcher(space, seed=42)
    searcher = WarmStartSearcher(base, [{"x": 0.1}])

    assert searcher.propose(0) == []
    assert searcher.n_seeds_remaining == 1


def test_warm_start_searcher_observe():
    """observe passes through to base."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    base = SobolSearcher(space, seed=42)
    searcher = WarmStartSearcher(base, [{"x": 0.1}])

    # No crash, no assertion — observe is pass-through
    searcher.observe({"config": {"x": 0.1}, "value": 0.5})


def test_warm_start_searcher_state_dict_round_trip():
    """state_dict / load_state_dict preserves wrapper and base state."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    base = SobolSearcher(space, seed=42)
    seeds = [{"x": 0.1}, {"x": 0.2}, {"x": 0.3}]
    searcher = WarmStartSearcher(base, seeds)

    # Consume one seed
    searcher.propose(1)

    # Serialize
    state = searcher.state_dict()
    assert state["kind"] == "warm_start"
    assert state["n_seeds_total"] == 3
    assert state["n_seeds_used"] == 1
    assert len(state["seed_queue"]) == 2

    # Rebuild
    base2 = SobolSearcher(space, seed=99)  # different seed
    searcher2 = WarmStartSearcher(base2, [])
    searcher2.load_state_dict(state)

    assert searcher2.n_seeds_remaining == 2
    assert searcher2.n_seeds_used == 1
    # Next proposal drains remaining seeds
    batch = searcher2.propose(2)
    assert batch[0] == {"x": 0.2}
    assert batch[1] == {"x": 0.3}


def test_warm_start_searcher_load_state_wrong_kind():
    """load_state_dict raises on mismatched kind."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    base = SobolSearcher(space, seed=42)
    searcher = WarmStartSearcher(base, [])

    try:
        searcher.load_state_dict({"kind": "random", "base": {}})
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "cannot load state of kind 'random'" in str(e)


def test_warm_start_searcher_from_store():
    """from_store builds a searcher directly from the run store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        store.write_study(Study(
            study_id="study_1",
            space_json=space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))
        store.write_trial(Trial(
            trial_id="trial_0",
            config={"x": 0.2},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        base = SobolSearcher(space, seed=99)
        searcher = WarmStartSearcher.from_store(
            base, store, space, study_id="study_1", n=1, objective="minimize"
        )

        batch = searcher.propose(1)
        assert batch[0] == {"x": 0.2}

        store.close()


def test_warm_start_searcher_capabilities():
    """capabilities property delegates to base."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

    base = SobolSearcher(space, seed=42)
    searcher = WarmStartSearcher(base, [])

    assert searcher.capabilities == base.capabilities


def test_load_seed_configs_no_completed_trials():
    """A study that exists but has no completed trials yields no seeds."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        store.write_study(Study(
            study_id="study_1",
            space_json=space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))
        # Still running — get_best_trials filters to completed only
        store.write_trial(Trial(
            trial_id="trial_0",
            config={"x": 0.2},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=1.0,
            status="running",
        ), study_id="study_1")

        assert load_seed_configs(store, "study_1", space, n=5) == []

        store.close()


def test_load_seed_configs_from_all_studies_objective_mismatch():
    """Studies optimizing the other direction are not pooled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        store.write_study(Study(
            study_id="maximize_study",
            space_json=space.to_json(),
            objective="maximize",
            seed=42,
            budget=100.0,
        ))
        store.write_trial(Trial(
            trial_id="trial_0",
            config={"x": 0.2},
            seed=42,
            fidelity=1.0,
            value=0.9,
            cost=1.0,
            status="completed",
        ), study_id="maximize_study")

        # Asking for minimize skips the maximize study rather than mixing directions
        assert load_seed_configs_from_all_studies(store, space, objective="minimize") == []
        # Asking for maximize finds it
        assert load_seed_configs_from_all_studies(store, space, objective="maximize") == [
            {"x": 0.2}
        ]

        store.close()


def test_load_seed_configs_from_all_studies_incompatible_space():
    """Structurally incompatible studies are short-circuited before loading trials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        source_space = SearchSpace()
        source_space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        store.write_study(Study(
            study_id="study_1",
            space_json=source_space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))
        store.write_trial(Trial(
            trial_id="trial_0",
            config={"x": 0.2},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        # Target has an extra knob: not structurally compatible
        target_space = SearchSpace()
        target_space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))
        target_space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 1.0)))

        assert load_seed_configs_from_all_studies(store, target_space) == []

        store.close()


def test_load_seed_configs_from_all_studies_skips_null_and_invalid():
    """Trials with no value, or configs outside the target bounds, are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        store.write_study(Study(
            study_id="study_1",
            space_json=space.to_json(),
            objective="minimize",
            seed=42,
            budget=100.0,
        ))
        # Completed but no recorded objective value
        store.write_trial(Trial(
            trial_id="trial_null",
            config={"x": 0.2},
            seed=42,
            fidelity=1.0,
            value=None,
            cost=1.0,
            status="completed",
        ), study_id="study_1")
        # Same declared space, but the recorded value is outside the knob bounds
        store.write_trial(Trial(
            trial_id="trial_oob",
            config={"x": 5.0},
            seed=42,
            fidelity=1.0,
            value=0.1,
            cost=1.0,
            status="completed",
        ), study_id="study_1")
        # The one usable seed
        store.write_trial(Trial(
            trial_id="trial_ok",
            config={"x": 0.7},
            seed=42,
            fidelity=1.0,
            value=0.3,
            cost=1.0,
            status="completed",
        ), study_id="study_1")

        seeds = load_seed_configs_from_all_studies(store, space, n=5)

        assert seeds == [{"x": 0.7}]

        store.close()


def test_load_seed_configs_from_all_studies_dedup():
    """The same config found in two studies is returned once, at its best rank."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        for study_id, seed, value in (("study_1", 42, 0.5), ("study_2", 99, 0.1)):
            store.write_study(Study(
                study_id=study_id,
                space_json=space.to_json(),
                objective="minimize",
                seed=seed,
                budget=100.0,
            ))
            store.write_trial(Trial(
                trial_id=f"{study_id}_trial",
                config={"x": 0.4},  # identical config in both studies
                seed=seed,
                fidelity=1.0,
                value=value,
                cost=1.0,
                status="completed",
            ), study_id=study_id)

        seeds = load_seed_configs_from_all_studies(store, space, n=5)

        assert seeds == [{"x": 0.4}]

        store.close()


def test_warm_start_searcher_from_store_all_studies():
    """from_store without study_id pools every compatible study."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        for study_id, seed, value, x in (
            ("study_1", 42, 0.5, 0.2),
            ("study_2", 99, 0.1, 0.8),
        ):
            store.write_study(Study(
                study_id=study_id,
                space_json=space.to_json(),
                objective="minimize",
                seed=seed,
                budget=100.0,
            ))
            store.write_trial(Trial(
                trial_id=f"{study_id}_trial",
                config={"x": x},
                seed=seed,
                fidelity=1.0,
                value=value,
                cost=1.0,
                status="completed",
            ), study_id=study_id)

        base = SobolSearcher(space, seed=7)
        searcher = WarmStartSearcher.from_store(base, store, space, n=2)

        assert searcher.n_seeds_remaining == 2
        batch = searcher.propose(2)
        assert batch == [{"x": 0.8}, {"x": 0.2}]  # best-first across studies

        store.close()


def test_warm_start_searcher_from_store_empty_degrades_to_cold():
    """An empty store degrades to the base searcher instead of failing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        warm = WarmStartSearcher.from_store(SobolSearcher(space, seed=7), store, space)
        assert warm.n_seeds_remaining == 0

        # Same points as a cold Sobol run with the same seed
        cold = SobolSearcher(space, seed=7)
        assert warm.propose(3) == cold.propose(3)

        store.close()
