"""A real local Ray worker preserves declared roles, metering and recovery."""
import json
from contextlib import closing

import pytest

ray = pytest.importorskip('ray')
from examples.declared_tuning import make_study
from hponas import RayExecutor
from hponas.store import Store


def test_live_declared_ray_metered_artifact_roles_and_resume(tmp_path):
    ray.init(num_cpus=1,include_dashboard=False,object_store_memory=100*1024*1024)
    try:
        with closing(Store(tmp_path/'ray.db')) as store:
            study = make_study(tmp_path,store)
            study.executor = RayExecutor(num_workers=1,max_retries=0)
            result = study.run()
            report = study.report()
            assert result.resources['tuning']['measured_work'] == 16
            assert result.resources['final']['measured_work'] == 2
            assert result.resources['tuning']['work_exact'] and result.resources['final']['work_exact']
            assert len(report['artifacts']) == 18
            assert not report['accounting']['uncertain_trial_ids']
            for row in report['artifacts']:
                saved = json.loads(open(row['path']).read())
                assert saved['role'] == row['role'] and saved['seed'] == row['seed']
            artifact_bytes = {row['path']:open(row['path'],'rb').read() for row in report['artifacts']}
            recovered = make_study(tmp_path,store)
            recovered.executor = RayExecutor(num_workers=1,max_retries=0)
            recovered.load_checkpoint()
            recovered.run()
            assert recovered.report() == report == store.read_report(study.study_name)
            assert {path:open(path,'rb').read() for path in artifact_bytes} == artifact_bytes
            assert ray.is_initialized()
    finally:
        ray.shutdown()


def test_live_ray_repeated_barriers_preserve_vector_and_scalar_roles(tmp_path):
    from tests.integration import test_declared_streaming as fixtures
    from hponas import (MultiObjectiveStudy, MultiObjectiveRandomSearcher, MultiObjectiveScheduler,
                        EvaluationObjective, StudyBudget)
    ray.cloudpickle.register_pickle_by_value(fixtures)
    ray.init(num_cpus=1, include_dashboard=False, object_store_memory=100*1024*1024)
    try:
        from hponas.schedulers import ASHAConfig, ASHAScheduler
        declaration = fixtures.declaration(tuning_folds=(fixtures.declaration().tuning_folds[0],),
            final_seeds=(10,), streaming_steps=(1., 2.))
        scalar = fixtures.make(budget=1, declaration=declaration,
            scheduler=ASHAScheduler(ASHAConfig(r_min=2, r_max=2)),
            executor=RayExecutor(num_workers=1, max_retries=0),
            resource_budget=StudyBudget(1, 'gradient_updates', 8, 4, 2), checkpoint_dir=tmp_path)
        result = scalar.run()
        assert result.evaluation['outcome'] == 'completed'
        assert result.resources['final']['measured_work'] == 2
        assert result.resources['tuning']['work_exact']
        contract = dict(objectives=fixtures.VECTOR, constraints={'eta': .5}, work_unit='gradient_updates')
        declaration = fixtures.declaration(objectives=(EvaluationObjective('loss', 'min', 'units'),
            EvaluationObjective('size', 'min', 'parameters')), streaming_steps=(1., 2.),
            tuning_folds=(fixtures.declaration().tuning_folds[0],), final_seeds=(10,))
        vector = MultiObjectiveStudy(MultiObjectiveRandomSearcher(fixtures.space(), seed=1, **contract),
            RayExecutor(num_workers=1, max_retries=0), fixtures.vector_objective, **contract, budget=1,
            declaration=declaration, continuation='resume',
            scheduler=MultiObjectiveScheduler(**contract, r_min=2, r_max=2))
        output = vector.run()
        assert output.front and output.evaluation['outcome'] == 'completed'
        assert all(r.metadata['multi_objective']['work'] == 4 for r in output.history)
        assert all('_final_' not in r.trial_id for r in vector.searcher.history)
        assert ray.is_initialized()
    finally:
        ray.shutdown()
