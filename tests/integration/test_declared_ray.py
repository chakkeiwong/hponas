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
