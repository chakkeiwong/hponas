"""Study-owned clusters have a separate scope from externally shared clusters.

Pytest may select tests in any order. A module-scoped external cluster must
finish teardown before this ownership contract expects an uninitialized Ray.
"""

import sys

import pytest

from hponas import IncompleteStudyError, RayExecutor, Study
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers import RandomSearcher
from hponas.space import SearchSpace, Knob

ray = pytest.importorskip("ray")
ray.cloudpickle.register_pickle_by_value(sys.modules[__name__])


def training(config, fidelity, resume_from, checkpoint, reporter):
    if resume_from:
        assert checkpoint == {"step": resume_from}
    for step in range(int(resume_from) + 1, int(fidelity) + 1):
        reporter(step, 5, cost=step - resume_from, checkpoint={"step": step})
    return {"value": 5, "cost": fidelity - resume_from}


def test_study_owns_cluster_across_streamed_batches_and_can_restart_it():
    assert not ray.is_initialized()
    for _ in range(2):
        # Ownership is a functional contract. Actor startup is bounded by the
        # surrounding test process, not an incidental per-trial deadline.
        executor = RayExecutor(num_workers=1, max_retries=0)
        study = Study(
            RandomSearcher(SearchSpace([Knob("x", "continuous", (0, 1))]), seed=9),
            executor,
            training,
            budget=2,
            continuation="resume",
            scheduler=ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=2)),
        )
        try:
            outcome = study.run()
        except IncompleteStudyError as error:
            pytest.fail(f"Ownership study incomplete: {error.result.history!r}")
        assert outcome.total_cost == 4
        assert executor._owns_ray and not ray.is_initialized()
