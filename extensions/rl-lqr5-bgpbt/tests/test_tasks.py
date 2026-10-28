import json
from pathlib import Path
import os
import pytest

from hponas.executors.resource_executor import ResourceExecutor
from hponas.executors.resources import ResourceSpec
from hponas_rl_bgpbt.tasks import read, run_task, task

CONFIG={'actor_hiddens':[8,8],'critic_hiddens':[8,8],'actor_lr':.001,'critic_lr':.001}


def test_commit_replay_and_uncertain_reservation(tmp_path):
    request=task(tmp_path/'committed','fresh',CONFIG,9,288)
    a=run_task(request); b=run_task(request)
    assert a==b and a['work']['transitions']==288
    cp=Path(request['directory'])/'checkpoint.pt'; stamp=cp.stat().st_mtime_ns
    assert run_task(request)==a and cp.stat().st_mtime_ns==stamp
    unknown=task(tmp_path/'uncertain','fresh',CONFIG,9,288)
    Path(unknown['directory']).mkdir()
    (Path(unknown['directory'])/'intent.json').write_text(json.dumps({'task':unknown}))
    with pytest.raises(RuntimeError,match='Uncertain'): run_task(unknown)
    cp.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='artifact'): run_task(request)


def test_actual_parallel_cpu_sac_and_cross_worker_resume(tmp_path):
    cpus=sorted(os.sched_getaffinity(0))[:2]
    assert len(cpus)==2, 'Two CPU cores required; no skip'
    requests=[task(tmp_path/str(i),'fresh',CONFIG,40+i,320,barrier=str(tmp_path/'barrier')) for i in range(2)]
    with ResourceExecutor(2,resources=ResourceSpec(),cpu_ids=cpus,timeout=150) as executor:
        results=executor.map(run_task,requests)
        resume=task(tmp_path/'resume','train',CONFIG,40,16,
                    input_path=tmp_path/'0/checkpoint.pt')
        resumed=executor.map(run_task,[resume])[0]
    overlap=min(r['training_finished_epoch'] for r in results)-max(r['training_started_epoch'] for r in results)
    assert overlap>0
    assert results[0]['pid']!=results[1]['pid']
    assert not set(results[0]['cpu_affinity']) & set(results[1]['cpu_affinity'])
    assert resumed['restore_identity']==results[0]['checkpoint_identity']
    assert resumed['work']['transitions']==16
