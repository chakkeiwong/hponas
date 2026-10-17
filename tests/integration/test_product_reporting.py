"""Complete public exports with independent work/front and artifact checks."""
from contextlib import closing, nullcontext
from copy import deepcopy
import json
import math
import sys

import pytest

from hponas import (Study, RandomSearcher, SearchSpace, Knob, LocalExecutor, RayExecutor,
                    StudyBudget, IncompleteStudyError)
from hponas.store import Store
from hponas.postgres import PostgresStore
from hponas.reporting import study_report
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.schedulers import ASHAScheduler, ASHAConfig
from tests.integration.test_declared_evaluation import declaration
from tests.unit.test_ray_control_paths import Transport


@pytest.mark.parametrize('mode',['sync','async'])
def test_complete_scalar_export_preserves_failures_final_and_artifacts(tmp_path,mode):
    def objective(config,seed,evaluation,trial_id):
        artifact=tmp_path/(trial_id+'.json')
        artifact.write_text(json.dumps({'x':config['x'],'role':evaluation.role,'seed':seed}))
        failed='_trial_0_' in trial_id and evaluation.role=='tuning'
        return dict(value=float('nan') if failed else config['x']**2+seed,cost=2.,
                    artifacts={'model':str(artifact)},metadata={'resource':{'work':1,'unit':'evaluations'}})
    with closing(Store(tmp_path/'study.sqlite')) as store:
        study=Study(RandomSearcher(SearchSpace([Knob('x','ordinal',(0,3))]),seed=21),
            LocalExecutor(mode=mode),objective,budget=3,maximize=False,study_name='export',
            declaration=declaration(),store=store,resource_budget=StudyBudget(3,'evaluations',12,4,1))
        result=study.run()
        report=study.report()
        assert report==store.read_report('export')
        assert len(report['trials'])==3 and report['trials'][0]['result']['status']=='failed'
        assert report['trials'][0]['result']['objective_value'] is None
        assert report['nonfinite_values'] and all(r['value']=='nan' for r in report['nonfinite_values'])
        assert report['selection']['state']=='frozen'
        assert report['selection']['trial_ids']==result.evaluation['selection']
        summaries=report['evaluation']['tuning']
        assert summaries[0]['status']=='failed'
        assert summaries[0]['objectives']['loss']=={'mean':None,'sample_std':None,'n':0}
        for row in summaries[1:]:
            x=study.trials[row['trial_id']].config['x']
            assert row['objectives']['loss']=={'mean':x*x+3.,'sample_std':math.sqrt(4/3),'n':4}
        assert report['resources']['tuning']['measured_work']==12
        assert report['resources']['final']['measured_work']==2
        assert report['accounting']['tuning']['recorded_cost']==24
        assert report['accounting']['final']['recorded_cost']==4
        curve=report['tuning_trajectory']['rows']
        assert [r['measured_work'] for r in curve]==[4,8,12]
        assert [r['recorded_cost'] for r in curve]==[8,16,24]
        assert curve[0]['incumbent_value'] is None
        assert curve[-1]['incumbent_value']==result.best_value
        assert len(report['artifacts'])==14
        assert {r['path'] for t in report['trials'] for r in store.read_artifacts(t['trial_id'])} == {
            r['path'] for r in report['artifacts']}
        for artifact in report['artifacts']:
            contents=json.loads(open(artifact['path']).read())
            assert contents['role']==artifact['role'] and contents['seed']==artifact['seed']
        path=tmp_path/'report.json'
        assert study.export_report(path)==report
        assert json.loads(path.read_text())==report
        with pytest.raises(FileExistsError): store.export_report('export',path)
        report['selection']['trial_ids'].clear()
        assert study.report()['selection']['trial_ids']
        assert store.read_report('absent') is None


def test_maintained_scalar_and_vector_examples_publish_public_reports(tmp_path):
    from examples.declared_tuning import run as scalar
    from examples.finance_tuning import run as vector
    a=scalar(tmp_path/'scalar')
    b=vector(tmp_path/'vector')
    assert a['workflow_report_schema']=='study_report_v1'
    assert a['best_value']>=0  # exact global squared-loss bound, no search success threshold
    assert b['metrics']['total_work']==64 and b['n_trials']==8
    report=json.loads((tmp_path/'vector/workflow-report.json').read_text())
    assert report['evaluation']['status']=='opted_out'
    assert report['selection']['trial_ids']==b['metrics']['front_trial_ids']
    assert report['resources']['tuning']['measured_work']==64
    points=[(t['trial_id'],t['vector']['objectives']) for t in report['trials']]
    oracle=[tid for tid,p in points if not any(
        q['variance']<=p['variance'] and q['expected_return']>=p['expected_return'] and
        (q['variance']<p['variance'] or q['expected_return']>p['expected_return']) for _,q in points)]
    assert report['selection']['trial_ids']==oracle
    assert [r['measured_work'] for r in report['tuning_trajectory']['rows']]==list(range(8,65,8))
    assert report['tuning_trajectory']['rows'][-1]['hypervolume']==b['metrics']['hypervolume']


def test_streaming_curves_checkpoint_transfer_and_replay_export(tmp_path):
    from workloads.streaming_quadratic import StreamingQuadratic
    from validation.multifidelity_reference import value as exact
    def searcher(): return RandomSearcher(SearchSpace([Knob('eta_index','ordinal',(1,25))]),seed=12)
    scheduler=ASHAScheduler(ASHAConfig(r_min=1,r_max=4,eta=2))
    events=EventLog(tmp_path/'events.jsonl'); workload=StreamingQuadratic()
    with closing(Store(tmp_path/'stream.sqlite')) as store:
        study=Study(searcher(),LocalExecutor(),workload,budget=4,max_concurrent=4,
                    maximize=False,continuation='resume',scheduler=scheduler,event_log=events,store=store)
        result=study.run()
        report=store.read_report(study.study_name)
        assert report==study.report()
        assert report['accounting']['tuning']['recorded_cost']==len(workload.updates)==result.total_cost
        for trial in report['trials']:
            for point in trial['progress']:
                assert point['value']==pytest.approx(float(exact(trial['config']['values']['eta_index'],int(point['fidelity']))),abs=1e-12)
        assert any(len(t['lineage'])>1 and t['result']['metadata']['checkpoint'] for t in report['trials'])
        replay=ReplayEngine(searcher(),events,12,ASHAScheduler(scheduler.config))
        assert replay.verify_determinism(4)[0]


def test_postgres_reporting_queries_read_without_coordinator_claim(tmp_path):
    from examples.declared_tuning import make_study
    with closing(Store(tmp_path/'sqlite.db')) as sqlite:
        study=make_study(tmp_path,sqlite); study.run()
        state=sqlite.load_study_snapshot(study.study_name)
        pg=object.__new__(PostgresStore)
        pg.peek_study_snapshot=lambda sid:deepcopy(state) if sid==study.study_name else None
        pg.load_study_snapshot=lambda sid:pytest.fail('Reporting acquired coordinator ownership')
        assert pg.read_evaluation(study.study_name)==sqlite.read_evaluation(study.study_name)
        assert pg.read_rung_diagnostics(study.study_name)==sqlite.read_rung_diagnostics(study.study_name)
        assert pg.read_report(study.study_name)==sqlite.read_report(study.study_name)
        assert pg.export_report(study.study_name,tmp_path/'pg.json')==study.report()
        assert pg.read_evaluation('absent') is pg.read_report('absent') is pg.read_rung_diagnostics('absent') is None


def test_ray_declared_context_and_transport_failure_are_durable(monkeypatch,tmp_path):
    from examples.declared_tuning import make_study
    transport=Transport(); monkeypatch.setitem(sys.modules,'ray',transport)
    study=make_study(tmp_path)
    study.executor=RayExecutor(num_workers=1,max_retries=0)
    result=study.run()
    assert result.evaluation['outcome']=='completed'
    assert result.resources['tuning']['measured_work']==16
    transport.outcomes=[RuntimeError('lost worker')]
    failed=make_study(tmp_path)
    failed.executor=RayExecutor(num_workers=1,max_retries=0)
    with pytest.raises(IncompleteStudyError): failed.run()
    report=failed.report()
    # One failed transport repetition exhausts metering; subsequent repetitions
    # are cancelled without dispatch, so the aggregate is cancelled/invalid.
    assert report['trials'][0]['result']['status']=='cancelled'
    assert report['evaluation_records']['tuning']['declared_example_trial_0'][0]['result']['status']=='failed'
    assert report['accounting']['uncertain_trial_ids']
    assert report['resources']['tuning']['charged_work']==1
    assert not report['resources']['tuning']['work_exact']
    restored=make_study(tmp_path)
    restored.load_checkpoint(tmp_path/'declared_example_checkpoint.json')
    assert restored.report()==report


def test_ray_hidden_retries_refused_before_metered_dispatch(monkeypatch):
    transport=Transport(); monkeypatch.setitem(sys.modules,'ray',transport)
    with pytest.raises(ValueError,match='max_retries=0'):
        Study(RandomSearcher(SearchSpace([Knob('x','ordinal',(0,3))])),RayExecutor(num_workers=1),
              lambda config,seed,evaluation:1.,declaration=declaration(),maximize=False,
              resource_budget=StudyBudget(3,'evaluations',12,4,1))
    assert transport.init_calls==[]


def test_incomplete_lineage_export_fails_instead_of_looping():
    from tests.unit.test_rung_diagnostics import ledger
    state=ledger(); state['budget']=3; state['searcher_state']={}
    state['trials']['root-0']['parent_trial_id']='root-0-full'
    with pytest.raises(ValueError,match='lineage'): study_report(state)


def test_serialized_declaration_does_not_accept_altered_policy_tags():
    from hponas import StudyDeclaration
    contract=declaration().contract
    assert StudyDeclaration.from_contract(contract).contract==contract
    for key,value in [('version',2),('aggregation','best_seed'),('constraint_policy','mean')]:
        changed={**contract,key:value}
        with pytest.raises(ValueError,match='policy or version'): StudyDeclaration.from_contract(changed)


def test_postgres_snapshot_preserves_twelve_trial_observation_order(tmp_path):
    # Exercise real PostgreSQL snapshot serialization over a text-column
    # transport double. The local-operations stage also checks a live server.
    saved = {}
    pg = object.__new__(PostgresStore)
    pg._loaded = set()
    pg._claim = lambda sid: None
    pg._transaction = nullcontext
    pg._upsert_study = lambda row: None
    pg._upsert_trial = lambda row, sid: None

    class Cursor:
        def __init__(self, row=None): self.row = row
        def fetchone(self): return self.row

    def execute(query, params):
        if query.startswith('INSERT INTO snapshots'):
            saved[params[0]] = params[1]
        elif query.startswith('SELECT payload FROM snapshots'):
            return Cursor((saved[params[0]],) if params[0] in saved else None)
        elif query.startswith('SELECT revision FROM snapshots'):
            return Cursor((1,) if params[0] in saved else None)
        return Cursor()

    pg._execute = execute

    def make():
        return Study(RandomSearcher(SearchSpace([Knob('x','ordinal',(0,20))]),seed=3),
                     LocalExecutor(),lambda config,seed,evaluation:config['x']**2,
                     budget=12,maximize=False,study_name='ordered',declaration=declaration(),store=pg)

    study = make()
    study.run()
    report = study.report()
    expected = ['ordered_trial_'+str(i) for i in range(12)]
    assert [r['last_trial_id'] for r in report['tuning_trajectory']['rows']] == expected
    assert pg.read_report('ordered') == report
    recovered = make()
    recovered.load_checkpoint()
    assert recovered.report() == report


def test_interrupted_declared_artifact_is_indexed_and_survives_sqlite_backup(tmp_path):
    from examples.declared_tuning import make_study
    from hponas.operations import backup_database, restore_database
    database = tmp_path/'source.db'
    with closing(Store(database)) as store:
        study = make_study(tmp_path,store)
        original = study.objective_fn
        calls = []
        def interrupted(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if len(calls) == 2:
                raise KeyboardInterrupt('interrupt during repetition group')
            return original(config,seed,evaluation,trial_id)
        study.objective_fn = interrupted
        with pytest.raises(KeyboardInterrupt): study.run()
        assert not study.results
        report = study.report()
        assert len(report['artifacts']) == 1
        assert store.read_artifacts('declared_example_trial_0')[0]['path'] == report['artifacts'][0]['path']
    backup_database(database,tmp_path/'backup')
    restore_database(tmp_path/'backup',tmp_path/'restored.db')
    with closing(Store(tmp_path/'restored.db')) as store:
        recovered = make_study(tmp_path,store)
        recovered.load_checkpoint()
        assert recovered.report() == report
        assert store.read_artifacts('declared_example_trial_0')[0]['path'] == report['artifacts'][0]['path']
