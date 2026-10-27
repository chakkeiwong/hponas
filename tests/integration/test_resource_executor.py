import os
import time
import pytest
from hponas.executors import ResourceExecutor
from hponas.types import Config, Trial


def identity(config, execution):
    import torch
    time.sleep(config.get('delay',0))
    return {'value':config['x']**2,'metadata':{'pid':os.getpid(),'cpus':sorted(os.sched_getaffinity(0)),
            'threads':torch.get_num_threads(),'cuda':os.environ.get('CUDA_VISIBLE_DEVICES'),
            'context':execution.to_dict(),'start':time.monotonic()}}


def test_process_isolation_order_and_persistence():
    trials=[Trial(Config({'x':i,'delay':.15}),str(i)) for i in range(4)]
    with ResourceExecutor(2,timeout=40) as executor:
        results=executor.execute_batch(trials,identity)
        assert [r.objective_value for r in results]==[0,1,4,9]
        assert all(r.is_valid() for r in results)
        pids={r.metadata['pid'] for r in results}; assert len(pids)==2
        placements={tuple(r.metadata['cpus']) for r in results};assert len(placements)==2
        assert all(r.metadata['threads']==1 and r.metadata['cuda']=='' for r in results)
        assert abs(results[0].metadata['start']-results[1].metadata['start'])<.14
        assert executor.execute(Trial(Config({'x':3}),'later'),identity).metadata['pid'] in pids
    assert all(not os.path.exists('/proc/'+str(pid)) for pid in pids)


def test_worker_crash_is_charged_and_replaced():
    with ResourceExecutor(1,timeout=40) as executor:
        bad=executor.execute(Trial(Config({}),'bad'),lambda c:os._exit(7))
        assert bad.status=='failed' and bad.cost>0
        assert bad.metadata['execution']['accounting']=='lower_bound_after_interruption'
        assert executor.execute(Trial(Config({'x':2}),'good'),identity).objective_value==4


def test_timeout_stops_worker_without_retry():
    with ResourceExecutor(1,timeout=40) as executor:
        executor.timeout=.2
        result=executor.execute(Trial(Config({}),'timeout'),lambda c:time.sleep(5))
        assert result.status=='timeout' and executor._workers==[None]


def test_arbitrary_map_order_and_error_cleanup():
    with ResourceExecutor(2,timeout=40) as executor:
        assert executor.map(lambda x,ctx:x*x,[3,1,2])==[9,1,4]
        with pytest.raises(Exception,match='ZeroDivisionError'):
            executor.map(lambda x,ctx:1/x,[0,1])


def test_streaming_stop_is_coordinator_owned():
    from hponas.executors.reporting import ReportDecision
    def objective(config, reporter, execution):
        reporter(.5, 2., cost=3.)
        raise AssertionError('Must stop at coordinator decision')
    seen=[]
    def stop(report):
        seen.append(report.trial_id)
        return ReportDecision('stop','bounded test')
    with ResourceExecutor(timeout=40) as executor:
        result=executor.execute(Trial(Config({}),'stream'),objective,on_report=stop)
    assert result.status=='pruned' and result.cost==3 and seen==['stream']


def test_two_executors_cannot_double_lease_resources():
    first=ResourceExecutor(1,timeout=40)
    second=ResourceExecutor(1,timeout=40)
    try:
        first.prepare()
        with pytest.raises(ValueError,match='lease'):second.prepare()
        first.shutdown()
        second.prepare()
        assert second.execute(Trial(Config({'x':2}),'lease'),identity).objective_value==4
    finally:
        first.shutdown();second.shutdown()


def test_replacement_survives_batch_collector_thread_exit():
    with ResourceExecutor(1, timeout=40) as executor:
        assert executor.execute_batch([Trial(Config({}), 'crash')], lambda c: os._exit(7))[0].status == 'failed'
        first = executor.execute_batch([Trial(Config({'x': 2}), 'new')], identity)[0]
        time.sleep(.1)
        second = executor.execute_batch([Trial(Config({'x': 3}), 'later')], identity)[0]
        assert first.is_valid() and second.is_valid()
        assert first.metadata['pid'] == second.metadata['pid']


def test_coordinator_death_stops_owned_worker_and_releases_lease(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    marker=tmp_path/'worker.pid'
    source = '''import os,time,sys
from pathlib import Path
from hponas import ResourceExecutor
ex=ResourceExecutor(1,timeout=40);ex.prepare()
Path(sys.argv[1]).write_text(str(ex._workers[0][0].pid))
time.sleep(60)
'''
    parent=subprocess.Popen([sys.executable,'-c',source,str(marker)])
    pid=None
    try:
        deadline=time.monotonic()+40
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
        assert marker.exists()
        pid=int(marker.read_text());parent.kill();parent.wait(timeout=5)
        deadline=time.monotonic()+5
        def alive():
            try:return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
            except FileNotFoundError:return False
        while alive() and time.monotonic()<deadline:time.sleep(.05)
        assert not alive()
        with ResourceExecutor(1,timeout=40) as replacement:
            assert replacement.execute(Trial(Config({'x':2}),'after-death'),identity).objective_value==4
    finally:
        if parent.poll() is None:parent.kill();parent.wait(timeout=5)
        if pid is not None:
            try:os.kill(pid,9)
            except ProcessLookupError:pass
