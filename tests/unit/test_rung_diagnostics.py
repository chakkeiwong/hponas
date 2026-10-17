"""Hand-derived paired ranks, selective censoring and public durable reports."""
from contextlib import closing
from copy import deepcopy
import json
import math

import pytest

from hponas.diagnostics import paired_rung_diagnostics, read_rung_diagnostics, midranks
from hponas import (Study, RandomSearcher, SearchSpace, Knob, LocalExecutor,
                    StudyDeclaration, EvaluationObjective, EvaluationFold)
from hponas.multi_objective import ObjectiveSpec
from hponas.schedulers import ASHAScheduler, ASHAConfig
from hponas.store import Store


def ledger(low=(1,2,3), full=(1,2,3)):
    state=dict(study_name='ranks', maximize=False, trials={}, results={}, roots={}, pending=[],
               finished=True, report_cache={}, scheduler_state=dict(config={'r_max':4.},rungs=[1.,4.],terminal={}))
    for i, (x,y) in enumerate(zip(low,full)):
        root=f'root-{i}'
        for tid,value,fidelity,parent in [(root,x,1.,None),(root+'-full',y,4.,root)]:
            state['trials'][tid]=dict(config={'values':{'x':i}},fidelity=fidelity,parent_trial_id=parent)
            state['roots'][tid]=root
            state['results'][tid]=dict(trial_id=tid,status='completed',objective_value=value,fidelity=fidelity,metadata={})
    return state


@pytest.mark.parametrize('low,full,expected,status',[
    ([1,2,3],[1,2,3],1.,'defined'),
    ([1,2,3],[3,2,1],-1.,'defined'),
    ([1,2,3],[1,3,2],.5,'defined'),
    ([1,1,3],[1,2,3],math.sqrt(3)/2,'defined'),
    ([1,1,3],[2,2,1],-1.,'defined'),
    ([1,1,1],[1,2,3],None,'constant_ranks'),
    ([1,2,3],[2,2,2],None,'constant_ranks'),
    ([],[],None,'insufficient_pairs'),
    ([1],[2],None,'insufficient_pairs'),
])
def test_hand_calculated_spearman_including_ties_and_undefined(low,full,expected,status):
    row=paired_rung_diagnostics(ledger(low,full))['rows'][0]
    assert row['spearman']==pytest.approx(expected) if expected is not None else row['spearman'] is None
    assert row['status']==status
    assert row['n_pairs']==row['n_rung_observed']==row['n_full_observed']==len(low)
    assert row['n_excluded']==0
    if low==[1,1,3]: assert [p['rung_rank'] for p in row['pairs']]==[1.5,1.5,3.]


def test_midranks_refuse_nonfinite_and_preserve_original_order():
    assert midranks([4.,1.,4.,2.])==[3.5,1.,3.5,2.]
    for bad in (float('nan'),float('inf'),True):
        with pytest.raises(ValueError): midranks([1.,bad])


def test_pruned_failed_cancelled_and_pending_are_not_imputed():
    state=ledger([1,2,3,4,5],[5,4,3,2,1])
    state['scheduler_state']['terminal']['root-0']='pruned'
    del state['results']['root-0-full']
    state['results']['root-1-full']['status']='failed'
    state['results']['root-2-full']['status']='cancelled'
    del state['results']['root-3-full']
    state['pending']=['root-3-full']
    row=paired_rung_diagnostics(state)['rows'][0]
    assert row['n_pairs']==1 and row['spearman'] is None
    assert row['n_roots']==row['n_rung_observed']==5
    assert row['n_full_observed']==1 and row['n_excluded']==4
    assert row['exclusion_counts']=={'full:cancelled':1,'full:failed':1,'full:pending':1,'full:pruned':1}
    assert row['pairs'][0]['root_trial_id']=='root-4'


def test_pasha_temporary_cap_and_protected_final_are_not_full_tuning_data():
    state=ledger()
    state['scheduler_state'].update(rungs=[1.,2.,4.],current_top=1)
    for tid in list(state['results']):
        if tid.endswith('full'):
            state['results'][tid]['fidelity']=state['trials'][tid]['fidelity']=2.
    before=paired_rung_diagnostics(state)
    state['evaluation']={'final':{'invented':{'value':-99999.}}}
    assert paired_rung_diagnostics(state)==before
    assert before['full_fidelity']==4. and len(before['rows'])==2
    assert all(r['n_full_observed']==0 and r['spearman'] is None for r in before['rows'])


def test_progress_deduplicates_endpoints_and_ignores_restarted_prefixes():
    state=ledger()
    state['report_cache']={'root-0':{'1.0':{'value':1.}},
                           'root-0-full':{'1.0':{'value':999.}}}
    row=paired_rung_diagnostics(state)['rows'][0]
    assert row['n_pairs']==3 and row['spearman']==1.
    assert len(row['pairs'][0]['rung_sources'])==2
    state['report_cache']['root-0']['1.0']['value']=12.
    row=paired_rung_diagnostics(state)['rows'][0]
    assert row['n_pairs']==2
    assert row['exclusion_counts']=={'rung:conflicting_measurements':1}


def test_progress_can_measure_lower_rung_but_cannot_replace_completed_full_result():
    state=ledger()
    del state['results']['root-0']
    state['report_cache']={'root-0':{'1.0':{'value':1.}}}
    assert paired_rung_diagnostics(state)['rows'][0]['n_pairs']==3
    del state['results']['root-0-full']
    state['report_cache']['root-0-full']={'4.0':{'value':1.}}
    assert paired_rung_diagnostics(state)['rows'][0]['n_pairs']==2


def test_changed_config_non_tuning_roles_and_conflicting_full_values_are_excluded():
    state=ledger()
    state['trials']['root-0-full']['config']['values']['x']=55
    state['results']['root-1-full']['metadata']={'evaluation':{'role':'final'}}
    state['trials']['extra']=deepcopy(state['trials']['root-2-full'])
    state['roots']['extra']='root-2'
    state['results']['extra']={**state['results']['root-2-full'],'trial_id':'extra','objective_value':10.}
    row=paired_rung_diagnostics(state)['rows'][0]
    assert row['n_pairs']==0
    assert row['exclusion_counts']=={'full:configuration_changed':1,'rung:configuration_changed':1,
                                     'full:non_tuning_role':1,'full:conflicting_measurements':1}


def test_vector_diagnostics_use_named_measurements_and_nested_rung_grid():
    state=ledger()
    spec=ObjectiveSpec([dict(name='loss',direction='min',lower=0,upper=10),
                        dict(name='quality',direction='max',lower=0,upper=10)])
    state['multi_objective']={'identity':spec.identity,'contract':spec.contract}
    state['scheduler_state']={'config':{'r_max':4.},'scheduler':state['scheduler_state']}
    for row in state['results'].values():
        value=row['objective_value']
        quality=value if row['fidelity']==1 else 4-value
        row['metadata']['multi_objective']=spec.observation(objectives={'loss':value,'quality':quality},constraints={},work=1)
        row['objective_value']=0.
    report=paired_rung_diagnostics(state)
    assert [(r['objective'],r['direction'],r['spearman']) for r in report['rows']]==[('loss','min',1.),('quality','max',-1.)]
    state['multi_objective']['identity']='wrong'
    with pytest.raises(ValueError,match='identity'): paired_rung_diagnostics(state)


def test_missing_old_lineage_or_grid_is_explicit_and_retained_projection_is_verified():
    state=ledger()
    state['rung_diagnostics']=paired_rung_diagnostics(state)
    assert read_rung_diagnostics(json.loads(json.dumps(state)))==state['rung_diagnostics']
    state['rung_diagnostics']['rows'][0]['spearman']=-1.
    with pytest.raises(ValueError,match='differ'): read_rung_diagnostics(state)
    del state['roots']
    assert paired_rung_diagnostics(state)['reason']=='missing_or_invalid_root_lineage'
    del state['scheduler_state']['rungs']
    assert paired_rung_diagnostics(state)['reason']=='missing_or_invalid_rung_grid'
    state['scheduler_state']=None
    assert paired_rung_diagnostics(state)['status']=='not_applicable'
    assert read_rung_diagnostics(None) is None


def public_study(fn, **kwargs):
    declaration=StudyDeclaration(objective_id='quadratic',model_id='identity',data_id='synthetic',protocol_id='ranks-v1',
        objectives=(EvaluationObjective('loss','min','squared_units'),),
        tuning_folds=(EvaluationFold('train',('fit',),('score',)),),
        final_folds=(EvaluationFold('heldout',('fit','score'),('sealed',)),),tuning_seeds=(3,),final_seeds=(9,))
    return Study(RandomSearcher(SearchSpace([Knob('x','continuous',(0.,1.))]),seed=11),LocalExecutor(),fn,
        maximize=False,budget=6,max_concurrent=6,study_name='public-ranks',declaration=declaration,
        scheduler=ASHAScheduler(ASHAConfig(r_min=1.,r_max=2.,eta=2)),**kwargs)


def objective(config,seed,evaluation,fidelity):
    return (-10000. if evaluation.role=='final' else 1.) * (config['x']-.7)**2/fidelity


def test_public_study_store_resume_persisted_report_and_final_separation(tmp_path):
    with closing(Store(tmp_path/'ranks.sqlite')) as store:
        expected=public_study(objective).run()
        calls=[]
        def interrupt(config,seed,evaluation,fidelity):
            calls.append(evaluation.role)
            if len(calls)==3: raise KeyboardInterrupt
            return objective(config,seed,evaluation,fidelity)
        run=public_study(interrupt,store=store)
        with pytest.raises(KeyboardInterrupt): run.run()
        restored=public_study(objective,store=store); restored.load_checkpoint()
        actual=restored.run()
        assert [r.objective_value for r in actual.history]==[r.objective_value for r in expected.history]
        report=restored.rung_diagnostics()
        assert report==store.read_rung_diagnostics('public-ranks')
        assert report==store.load_study_snapshot('public-ranks')['rung_diagnostics']
        row=report['rows'][0]
        assert row['n_pairs']>=2 and row['spearman']==1.
        assert row['n_pairs']+row['n_excluded']==6
        assert all(p['full_value']>=0 for p in row['pairs'])
    with closing(Store(tmp_path/'ranks.sqlite')) as store:
        assert store.read_rung_diagnostics('public-ranks')==report
        assert store.read_rung_diagnostics('absent') is None


def test_restore_refuses_corrupted_report_without_mutating_live_state(tmp_path):
    run=public_study(objective)
    run.run()
    before=deepcopy(run._snapshot())
    bad=deepcopy(before); bad['rung_diagnostics']['rows'][0]['spearman']=-1.
    path=tmp_path/'bad.json'; path.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='rung diagnostics differ'): run.load_checkpoint(path)
    assert run._snapshot()==before
    # A historical snapshot can omit the optional derived projection.
    del bad['rung_diagnostics']; path.write_text(json.dumps(bad))
    run.load_checkpoint(path)
    assert run.rung_diagnostics()==before['rung_diagnostics']
