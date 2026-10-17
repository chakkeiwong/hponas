"""Complete local Study reports, reconstructed from authoritative snapshots."""
from copy import deepcopy
import json
import math
from pathlib import Path

from hponas.diagnostics import read_rung_diagnostics
from hponas.evaluation import (EvaluationController, StudyDeclaration,
                               legacy_evaluation_report)
from hponas.types import Result


def _json_values(value, path, nonfinite):
    if isinstance(value, float) and not math.isfinite(value):
        nonfinite.append({'pointer': path, 'value': 'nan' if math.isnan(value) else '+inf' if value > 0 else '-inf'})
        return None
    if isinstance(value, dict):
        return {str(k): _json_values(v, path+'/'+str(k).replace('~','~0').replace('/','~1'), nonfinite)
                for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_values(v, path+'/'+str(i), nonfinite) for i,v in enumerate(value)]
    return value


def study_report(state):
    """Return a detached report; final-evaluation data is a reporting surface.

    Artifact paths are references, never fetched. This export is not a restart
    checkpoint: nonfinite numbers become null with explicit JSON pointers.
    Retain the authoritative Study checkpoint for resume and replay.
    """
    if state is None:
        return None
    state = deepcopy(state)
    spec = None
    if state.get('multi_objective'):
        from hponas.multi_objective import ObjectiveSpec
        contract = state['multi_objective']
        spec = ObjectiveSpec(**contract['contract'])
        if spec.identity != contract['identity']:
            raise ValueError('Report objective contract identity differs')
    evaluation = state.get('evaluation')
    if evaluation is not None:
        contract = evaluation['contract']
        declaration = StudyDeclaration.from_contract(contract)
        if declaration.identity != evaluation['identity']:
            raise ValueError('Report evaluation declaration identity differs')
        controller = EvaluationController(declaration, maximize=state['maximize'], spec=spec)
        controller.state = evaluation
        evaluated = controller.report()
    else:
        evaluated = legacy_evaluation_report()
    endpoint = state['scheduler_state']['config']['r_max'] if state.get('scheduler_state') else 1.
    raw_results = list(state['results'].values())
    metrics = spec.summarize([Result(**r) for r in raw_results], endpoint_fidelity=endpoint) if spec else None
    if metrics is not None:
        eligible = metrics['front_trial_ids']
    else:
        rows = [r for r in raw_results if r['status']=='completed' and r['fidelity']==endpoint and
                type(r['objective_value']) in (int,float) and math.isfinite(r['objective_value'])]
        best = (max if state['maximize'] else min)(rows,key=lambda r:r['objective_value'],default=None)
        eligible = [best['trial_id']] if best else []
    frozen = evaluation is not None and evaluation['phase'] != 'tuning'
    selection = {'state': 'frozen' if frozen else 'provisional' if evaluation else 'legacy_unqualified',
                 'trial_ids': list(evaluation['selection']) if frozen else eligible,
                 'full_tuning_fidelity': endpoint}
    trials, artifacts = [], []
    for tid, trial in state['trials'].items():
        result = state['results'].get(tid)
        curve = [{'fidelity':float(step), **value} for step,value in state.get('report_cache',{}).get(tid,{}).items()]
        curve.sort(key=lambda row:row['fidelity'])
        path, current = [], tid
        while current is not None:
            if current in path or current not in state['trials']:
                raise ValueError('Report lineage is cyclic or incomplete')
            path.append(current)
            current = state['trials'][current].get('parent_trial_id')
        trials.append({**trial, 'root_trial_id':state.get('roots',{}).get(tid),
                       'lineage':path, 'result':result, 'progress':curve,
                       'vector':result.get('metadata',{}).get('multi_objective') if result else None})
        if evaluation is None and result is not None:
            artifacts.extend({'role':'tuning','trial_id':tid,'candidate_id':tid,'kind':kind,'path':value}
                             for kind,value in result.get('metadata',{}).get('artifacts',{}).items())
    if evaluation is not None:
        for role in ('tuning','final'):
            for tid, rows in evaluation[role].items():
                for row in rows:
                    result = row['result']
                    artifacts.extend({'role':role,'trial_id':result['trial_id'],'candidate_id':tid,
                                      'fold':row['fold'],'seed':row['seed'],'kind':kind,'path':value}
                                     for kind,value in result.get('metadata',{}).get('artifacts',{}).items())
    resources = state.get('resources')
    if resources is not None:
        from hponas.budgets import StudyBudget, ResourceController
        budget = StudyBudget(**{k:v for k,v in resources['contract'].items() if k!='version'})
        resource_controller = ResourceController(budget)
        resource_controller.state = resources
        resource_report = resource_controller.report()
    else:
        resource_report = {'mode':'legacy_controls','configuration_limit':state['budget'],
                           'work_unit':None,'final_work_reserved':False}
    # Raw declared repetitions include already committed but not yet aggregated
    # tuning calls. Counting both repetitions and aggregates would double-charge.
    def costs(role):
        rows = ([r['result'] for group in evaluation[role].values() for r in group]
                if evaluation is not None else raw_results if role=='tuning' else [])
        missing = [r['trial_id'] for r in rows if 'elapsed_seconds' not in r.get('metadata',{}).get('execution',{})]
        return dict(recorded_cost=math.fsum(r['cost'] for r in rows),
                    cost_unit='caller_reported_cost_or_executor_seconds',
                    recorded_elapsed_seconds=math.fsum(r.get('metadata',{}).get('execution',{}).get('elapsed_seconds',0.) for r in rows),
                    missing_elapsed_trial_ids=missing)
    trajectory = []
    for i, row in enumerate(raw_results):
        prefix = raw_results[:i+1]
        if spec is not None:
            summary = spec.summarize([Result(**r) for r in prefix], endpoint_fidelity=endpoint)
            point = {'front_trial_ids':summary['front_trial_ids'],'hypervolume':summary['hypervolume'],
                     'measured_work':summary['known_work_lower_bound'],'work_exact':summary['exact_work'],
                     'work_unit':spec.contract['work_unit']}
        else:
            valid = [r for r in prefix if r['status']=='completed' and r['fidelity']==endpoint and
                     type(r['objective_value']) in (int,float) and math.isfinite(r['objective_value'])]
            incumbent = (max if state['maximize'] else min)(valid,key=lambda r:r['objective_value'],default=None)
            point = {'incumbent_trial_id':incumbent['trial_id'] if incumbent else None,
                     'incumbent_value':incumbent['objective_value'] if incumbent else None,
                     'measured_work':None,'work_exact':False,'work_unit':None}
        if resources is not None:
            repetition_ids = {item['result']['trial_id'] for r in prefix for item in evaluation['tuning'].get(r['trial_id'],[])}
            attempts = [a for a in resources['attempts'] if a['role']=='tuning' and a['trial_id'] in repetition_ids]
            point.update(measured_work=math.fsum(a['work'] for a in attempts if a['work'] is not None),
                         charged_work=math.fsum(a['work'] if a['work'] is not None else resources['contract']['max_work_per_call'] for a in attempts),
                         work_exact=all(a['work'] is not None for a in attempts),work_unit=resources['contract']['work_unit'])
        trajectory.append({**point,'observation_count':i+1,'last_trial_id':row['trial_id'],
            'recorded_cost':math.fsum(r['cost'] for r in prefix),
            'recorded_elapsed_seconds':math.fsum(r.get('metadata',{}).get('execution',{}).get('elapsed_seconds',0.) for r in prefix),
            'elapsed_complete':all('elapsed_seconds' in r.get('metadata',{}).get('execution',{}) and
                                   r['metadata']['execution'].get('accounting')!='lower_bound_after_interruption' for r in prefix)})
    status = state.get('outcome') or ('completed' if state.get('finished') else 'running')
    if evaluated.get('outcome') in {'failed','infeasible','incomplete'}:
        status = 'final_evaluation_'+evaluated['outcome']
    report = dict(schema='study_report_v1', study_id=state['study_name'], status=status,
        stop_reason=state.get('stop_reason'), space=state.get('space'),
        declaration=evaluation['contract'] if evaluation else None, evaluation=evaluated,
        evaluation_records=evaluation, selection=selection, trials=trials, artifacts=artifacts,
        metrics=metrics, rung_diagnostics=read_rung_diagnostics(state), resources=resource_report,
        tuning_trajectory={'order':'observation_commit','time_scope':'sum of recorded evaluation elapsed, not parallel wall time',
                           'rows':trajectory},
        accounting={'tuning':costs('tuning'),'final':costs('final'),
            'uncertain_trial_ids':sorted(set(state.get('accounting_incomplete',[])) | set((evaluation or {}).get('uncertain',[]))),
            'inflight_repetition':(evaluation or {}).get('inflight'),
            'live_elapsed':state.get('live_elapsed',{}),'abandoned_elapsed':state.get('abandoned_elapsed',{}),
            'live_cost':state.get('live_cost',{}),'abandoned_cost':state.get('abandoned_cost',{})},
        admission=state.get('admission'), events=state.get('events',[]),
        scheduler=state.get('scheduler_state'),
        replay={'searcher_class':state.get('searcher_class'),'scheduler_class':state.get('scheduler_class'),
                'seed':state.get('searcher_state',{}).get('seed'),'continuation':state.get('continuation'),
                'resume_source':'authoritative Study checkpoint, not this reporting export'},
        claim='declared local workflow evidence; no application validity or production qualification')
    nonfinite = []
    report = _json_values(report,'',nonfinite)
    report['nonfinite_values'] = nonfinite
    return report


def export_study_report(state, destination):
    """Write strict JSON to a new file; refuse to overwrite prior output."""
    report = study_report(state)
    if report is None:
        raise ValueError('No stored study snapshot')
    payload = json.dumps(report,indent=2,allow_nan=False)+'\n'
    with Path(destination).open('x') as output:
        output.write(payload)
    return report
