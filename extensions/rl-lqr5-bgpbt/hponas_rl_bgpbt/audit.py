"""Read-only evidence reconstruction, independent of the population controller."""
from copy import deepcopy
from dataclasses import asdict
from itertools import product
import json
import math
from pathlib import Path

import numpy as np
import torch

from hponas.population_gp import TemporalOptions, TemporalPopulationGP
from hponas_rl_lqr5.reference import LQR5Spec, condensed_reference, numerical_tolerance, oracle_report
from hponas_rl_lqr5.search import validate
from .adapter import SACMember, digest
from .tasks import read, sha, write

ROOT=Path(__file__).resolve().parents[3]
EXT=ROOT/'extensions/rl-lqr5-bgpbt'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-03'
CORE='fb5a83647bd5d73aaff21e360bab73432c670c6b08038e52507749a7de99e320'


def require(ok,message):
    if not ok: raise ValueError(message)


def independently_score(actor_path):
    """Enumerate primitive signs directly and use independent condensed matrices."""
    actor=torch.jit.load(str(actor_path),map_location='cpu').eval()
    spec=LQR5Spec(); ref=condensed_reference(spec)
    signs=np.array(list(product((-1.,1.),repeat=13)))
    state=signs[:,:5]*.5; costs=np.zeros(len(state)); advantages=np.zeros(len(state))
    for t in range(8):
        obs=np.column_stack((state,np.full(len(state),(8-t)/8))).astype(np.float32)
        unique,inverse=np.unique(obs,axis=0,return_inverse=True)
        with torch.no_grad(): action=actor(torch.from_numpy(unique)).numpy()[inverse].astype(float)
        require(action.shape==(8192,1) and np.isfinite(action).all() and np.abs(action).max()<=1.,
                'Invalid exported actor action')
        costs+=.99**t*(np.sum(state*state,axis=1)+.1*action[:,0]**2)
        delta=action+state@ref['K'][t].T
        curvature=float((spec.R+.99*spec.B.T@ref['P'][t+1]@spec.B)[0,0])
        advantages+=.99**t*curvature*delta[:,0]**2
        state=state@spec.A.T+action@spec.B.T+signs[:,5+t,None]*spec.noise_vector
    costs+=.99**8*np.sum(state*state,axis=1)
    cost=math.fsum(costs)/8192; gap=cost-ref['optimal_cost']; adv=math.fsum(advantages)/8192
    tolerance=numerical_tolerance(spec,cost)
    require(abs(gap-adv)<=tolerance and gap>=-tolerance,'Independent performance identity failed')
    return {'cost':cost,'gap':gap,'advantage_gap':adv,'tolerance':tolerance,'paths':8192}


def verify_task(directory,result=None):
    directory=Path(directory); r=read(directory/'result.json') if result is None else result
    require(r['passed'],'Failed task')
    validate(r['task']['config'])
    require(r['task']['directory']==str(directory),'Task directory mismatch')
    require(read(directory/'intent.json')['task']==r['task'],'Task intent changed')
    for name,value in r['artifacts'].items(): require(sha(directory/name)==value,'Task artifact changed')
    score=independently_score(directory/'actor.pt')
    for k in ('cost','gap','advantage_gap'):
        require(abs(score[k]-r['score'][k])<=score['tolerance'],'Independent score differs')
    state=torch.load(directory/'checkpoint.pt',map_location='cpu',weights_only=False)
    require(SACMember.identity(state)==r['checkpoint_identity'],'Checkpoint scientific identity differs')
    require(state['config']==r['task']['config'],'Checkpoint configuration differs')
    require(state['transitions']==r['after']['transitions'] and state['updates']==r['after']['sac_updates'],
            'Checkpoint counters differ')
    actor=torch.jit.load(str(directory/'actor.pt')).state_dict()
    exported={k.replace('encoder.','pi_encoder.',1) if k.startswith('encoder.')
              else k.replace('head.','pi.',1):v for k,v in actor.items()}
    require(all(torch.equal(v,state['module'][k]) for k,v in exported.items()),'Actor differs from checkpoint')
    work=r['work']; transitions=r['after']['transitions']-r['before']['transitions']
    updates=r['after']['sac_updates']-r['before']['sac_updates']
    distillation=r['task'].get('distillation_steps',0)
    require(work=={'transitions':transitions,'sac_updates':updates,'distillation_updates':distillation,
                   'gradient_components':4*updates+3*distillation},'Work omitted or changed')
    require(transitions==r['task']['transitions'],'Transition request not fulfilled')
    if r['task'].get('input'):
        require(sha(r['task']['input'])==r['task']['input_sha256'],'Input checkpoint changed')
    if r['transfer']:
        tr=r['transfer']
        if tr['kind']=='changed_shape_distillation':
            teacher=torch.load(r['task']['input'],map_location='cpu',weights_only=False)
            require(tr['teacher_unchanged'] and SACMember.identity(teacher)==tr['teacher_identity'],
                    'Teacher identity changed')
            require(tr['steps']==distillation and tr['gradient_components']==3*distillation,
                    'Distillation work omitted')
            require(sum(tr['final_losses'])<=sum(tr['initial_losses'])+1e-6,'Best distillation snapshot lost')
            require(tr['adam_policy']=='reset_all' and tr['target_policy']=='hard_copy_online_after_distillation',
                    'Transfer state policy differs')
    return {'directory':str(directory),'score':score,'work':work,'config':state['config']}


def verify_proposal(record):
    gp=TemporalPopulationGP(list(range(2,13)),[0,1],TemporalOptions(**record['kernel']))
    if record['observed_points']: gp.observe(record['observed_points'],record['observed_improvements'])
    rows=[]
    for c in record['candidates']:
        validate(c)
        row=[record['time'],len(c['actor_hiddens']),len(c['critic_hiddens'])]
        for side in ('actor','critic'):
            widths=c[side+'_hiddens']; row += [(w-7)/57 for w in widths]+[0.]*(4-len(widths))
        row += [(math.log10(c[s+'_lr'])+5)/3 for s in ('actor','critic')]
        row += [math.log1p(record['cost_context'])]; rows.append(row)
    require(rows==record['points'],'Conditional proposal encoding differs')
    mean,var=gp.predict(rows)
    require(np.allclose(mean,record['mean'],rtol=0,atol=1e-10) and
            np.allclose(var,record['variance'],rtol=0,atol=1e-10),'Proposal posterior differs')
    selected=[]; pending=[]
    expected=record.get('bo_indices',record['selected_indices'])
    for _ in expected:
        m,v=gp.predict(rows,pending=pending); score=m+2*np.sqrt(v)
        score[selected]=-np.inf; idx=int(np.argmax(score)); selected.append(idx); pending.append(rows[idx])
    require(selected==expected,'Acquisition selection differs')
    if record.get('schema')==2:
        random_indices=record['random_indices']
        require(selected+random_indices==record['selected_indices'] and
                len(set(selected+random_indices))==len(record['selected_indices']) and
                all(type(i) is int and 0<=i<len(rows) for i in random_indices),'Random proposal mixture differs')
        if record['architecture']:
            require(record['response']=='negative_log1p_best_objective' and
                    record['time']==record['cost_context']==0,'Architecture response contract differs')
        if record['restart']:
            restart=record['restart']
            global_gp=TemporalPopulationGP(list(range(2,13)),[0,1],TemporalOptions(**restart['kernel']))
            global_gp.observe(restart['observed_points'],restart['observed_values'])
            m,v=global_gp.predict(restart['points'])
            require(int(np.argmax(m+2*np.sqrt(v)))==restart['index'] and not record['observed_points'],
                    'Global restart or local history reset differs')
    require(record['global_optimum'] is False,'Unsupported global acquisition claim')
    return selected


def verify_selection_v2(report):
    require(report['schema'] in (2,3) and report['estimand']=='complete_tuning_procedure',
            'Static configuration evidence is not procedure evidence')
    rule='best_evaluated_trained_checkpoint' if report['schema']==3 else 'best_evaluated_checkpoint'
    require(report['selection_rule']==rule and report['global_optimum'] is False,
            'Unsupported selection or global claim')
    require(len(report['events'])==3,'Population event count differs')
    for event in report['events']: verify_proposal(event['proposal'])
    generation=report['events'][1]; segment=report['segment_transitions']
    require(generation['criterion']=='exact_objective_after_sac','Wrong architecture selection objective')
    candidates=[read(Path(d)/'result.json') for d in generation['candidate_results']]
    require(len(candidates)==4,'Missing architecture candidates')
    for r,index in zip(candidates,generation['proposal']['selected_indices']):
        require(r['task']['config']==generation['proposal']['candidates'][index],'Candidate differs from proposal')
        require(r['work']['transitions']==segment//2 and r['work']['sac_updates']==segment//8 and
                r['work']['distillation_updates']==64,'Candidate missing actual joint SAC/transfer work')
        rates=r['after']['rates']; c=r['task']['config']
        require(rates['policy']==c['actor_lr'] and rates['qf']==rates['qf_twin']==c['critic_lr'],
                'Candidate SAC rates differ from proposal')
    order=sorted(range(4),key=lambda i:(candidates[i]['score']['cost'],i))
    require(order==generation['halving_order'] and order[:2]==generation['kept'],'Objective halving differs')
    for path,index in zip(generation['student_results'],generation['kept']):
        r=read(Path(path)/'result.json')
        require(r['task']['kind']=='train' and r['task']['input']==str(Path(candidates[index]['task']['directory'])/'checkpoint.pt')
                and r['work']['transitions']==segment//2,'Survivor continuation differs')
    for method,paths in [('bgpbt',report['population_results']),('baseline',report['baseline_results'])]:
        require(len(paths)==len(set(paths)),'Duplicate task accounting')
        records=[read(Path(d)/'result.json') for d in paths]
        require(len(records)==(24 if method=='bgpbt' else 20),'Missing procedure tasks')
        totals={k:sum(r['work'][k] for r in records) for k in report['work'][method]}
        require(totals==report['work'][method],'Procedure work omitted')
        eligible=[r for r in records if r['work']['sac_updates']>0] if report['schema']==3 else records
        winner=min(eligible,key=lambda r:(r['score']['cost'],r['task']['directory']))
        require(report['selected'][method]=={'config':winner['task']['config'],
            'task':winner['task']['directory'],'cost':winner['score']['cost']},'Best checkpoint selection differs')
    for key in ('transitions','gradient_components'):
        require(report['work']['bgpbt'][key]==report['work']['baseline'][key],'Unequal procedure work')
    require(report['work']['bgpbt']['transitions']==19*segment,'Wrong procedure transition allocation')
    require(report['work']['bgpbt']['distillation_updates']==256,'Wrong transfer allocation')


def verify_procedure(report):
    from itertools import product as signs
    require(report['estimand']=='complete_tuning_procedure' and report['seeds']==[9211,9212,9213],
            'Procedure replication contract differs')
    require(len(report['studies'])==3,'Incomplete procedure replications')
    differences=[]; tasks=[]
    for path,seed in zip(report['studies'],report['seeds']):
        study=read(path); verify_selection_v2(study)
        require(study['seed']==seed and study['segment_transitions']==2048,'Procedure seed or budget changed')
        differences.append(study['selected']['bgpbt']['cost']-study['selected']['baseline']['cost'])
        tasks+=study['population_results']+study['baseline_results']
    require(differences==report['paired_cost_differences_bgpbt_minus_baseline'],'Procedure difference changed')
    statistic=abs(float(np.mean(differences)))
    p=sum(abs(float(np.mean(np.array(s)*differences)))>=statistic-1e-15 for s in signs((-1,1),repeat=3))/8
    require(p==report['paired_sign_randomization_two_sided_p'],'Procedure diagnostic differs')
    require(report['global_optimum'] is False and report['superiority_established'] is False,
            'Unsupported procedure claim')
    return tasks


def verify_selection(report):
    require(report['global_optimum'] is False and report['all_attempts_retained'],'Unsupported search claim')
    for event in report['events']: verify_proposal(event['proposal'])
    require([e['kind'] for e in report['events']]==['compatible_exploit','architecture_generation','compatible_exploit'],
            'Population event sequence differs')
    generation=report['events'][1]
    candidates=[read(Path(d)/'result.json') for d in generation['candidate_results']]
    ranking=sorted(range(4),key=lambda i:(sum(candidates[i]['transfer']['final_losses']),i))
    require(ranking==generation['halving_order'] and generation['kept']==ranking[:2],'Distillation halving differs')
    for method,paths in [('bgpbt',report['population_results']),('baseline',report['baseline_results'])]:
        require(len(paths)==len(set(paths)),'Duplicate task accounting')
        records=[read(Path(d)/'result.json') for d in paths]
        total={k:sum(r['work'][k] for r in records) for k in report['work'][method]}
        require(total==report['work'][method],'Search work omitted')
        finals=report['snapshots'][-1]['members'] if method=='bgpbt' else paths
        final_results=[read(Path(d)/'result.json') for d in finals]
        selected=min(range(4),key=lambda i:(final_results[i]['score']['cost'],i))
        winner=final_results[selected]
        require(report['selected'][method]=={'config':winner['task']['config'],'task':finals[selected],
                                             'cost':winner['score']['cost']},'Selection differs')
    require(report['work']['bgpbt']['transitions']==report['work']['baseline']['transitions'],
            'Unequal transition allocation')
    require(report['work']['bgpbt']['gradient_components']==report['work']['baseline']['gradient_components'],
            'Unequal component minibatch allocation')
    require(report['confirmation']=={'seeds':[801,802,803],'estimand':'fresh_training_of_final_static_config',
        'budget':report['budget_per_initial_member'],'lineage_replay':False},'Confirmation freeze differs')


def source_closure(directory):
    directory=Path(directory); m=read(directory/'manifest.json'); r=read(directory/'receipt.json')
    for b in [m['runner'],*m['inputs']]:
        require(sha(directory/'inputs'/b['path'])==b['sha256'],'Archived source changed')
    require(r['core_source']==r['end_core_source']==CORE,'Core source changed')
    require(r['inputs_unchanged'],'Operation inputs changed')
    if r['passed']:
        require(not r['remaining_children'] and r['stop_reason'] is None,'Successful operation did not close cleanly')
    elif r['remaining_children'] or r['stop_reason'] is not None:
        from .operations import evidence
        cleanup=read(evidence('hardware-startup-cleanup'))
        require(cleanup['receipt']['sha256']==sha(directory/'receipt.json') and
                not cleanup['live_recorded_descendants'] and cleanup['startup_only'],
                'Failed operation lacks independent cleanup evidence')
    require(sha(ROOT/r['log']['path'])==r['log']['sha256'],'Log changed')
    if (directory/'work.jsonl').exists():
        ledger=[json.loads(l) for l in (directory/'work.jsonl').read_text().splitlines()]
        reservations={r['id']:r['work'] for r in ledger if r['event']=='reserve'}
        completed={r['id'] for r in ledger if r['event']=='complete'}
        if r['passed']: require(set(reservations)==completed,'Unresolved work reservation')
        totals={k:sum(w[k] for w in reservations.values()) for k in m['work_limits']}
        require(totals==r['charged_work'],'Operation ledger differs')
        require(all(totals[k]<=m['work_limits'][k] for k in totals),'Operation allocation exceeded')
    return r


def verify_hardware(report):
    require(report.get('passed') is True,'Hardware incomplete')
    require(len(set(report['physical_gpu_ids']))==2,'Two physical GPUs not verified')
    admission=report['admission']
    require(admission['passed'] and admission['idle_required'] is False,'Shared device admission missing')
    results=[read(Path(p)/'result.json') for p in report['results']]
    require(all(r['after']['device']=='cuda:0' for r in results),'GPU training absent')
    require({r['cuda_visible_devices'] for r in results}==set(report['physical_gpu_ids']),
            'GPU visibility differs')
    require(results[0]['pid']!=results[1]['pid'] and not set(results[0]['cpu_affinity']) & set(results[1]['cpu_affinity']),
            'Workers overlap physical assignment')
    overlap=min(r['training_finished_epoch'] for r in results)-max(r['training_started_epoch'] for r in results)
    require(overlap>0 and overlap==report['training_overlap_seconds'],'GPU training did not overlap')
    for key in ('rate_proposal','shape_proposal'): verify_proposal(report[key])
    descendants=[read(Path(p)/'result.json') for p in report['descendants']]
    require([r['transfer']['kind'] for r in descendants]==['compatible_copy','changed_shape_distillation'],
            'Both GPU transfer contracts required')
    require(all(r['after']['device']=='cuda:0' for r in descendants),'Transferred members not on GPU')
    require({r['cuda_visible_devices'] for r in descendants}==set(report['physical_gpu_ids']),
            'Transferred members lack distinct devices')
    overlap=min(r['training_finished_epoch'] for r in descendants)-max(r['training_started_epoch'] for r in descendants)
    require(overlap>0 and overlap==report['transfer_training_overlap_seconds'],'Transferred GPU training did not overlap')
    require(descendants[1]['work']['distillation_updates']==64,'GPU distillation work differs')
    for r in results+descendants:
        mem=r['gpu_memory']
        require(mem and 0<mem['peak_allocated_bytes']<=mem['peak_reserved_bytes']<=mem['allocator_limit_bytes']==1024**3,
                'Shared GPU allocator evidence missing')
        require(r.get('ray_initialized') is False,'Unexpected worker Ray cluster')
    resumed=read(Path(report['cpu_resume'])/'result.json')
    require(resumed['after']['device']=='cpu' and resumed['work']['sac_updates']>0,'CPU continuation absent')
    total={k:sum(r['work'][k] for r in results+descendants+[resumed]) for k in report['work']}
    require(total==report['work'],'Hardware work omitted')


def audit(out):
    from .operations import evidence
    from tools.source_identity import source_digest
    require(source_digest(ROOT)==CORE,'Qualified core changed')
    roles=('engineering','calibration','search','confirmation','hardware','documentation',
           'repair-engineering','procedure-check','device-repair')
    entries={role:evidence(role) for role in roles}
    for path in entries.values(): require(source_closure(path.parent)['passed'],'Required operation failed')
    selection=read(entries['search']); verify_selection(selection)
    calibration=read(entries['calibration'])
    curves=calibration['curves']; budget=8192 if np.median(curves[-1]['costs'])<np.median(curves[-2]['costs']) else 4096
    require(budget==calibration['budget_per_member']==selection['budget_per_initial_member'],'Budget freeze differs')
    confirm=read(entries['confirmation'])
    require(confirm['selection_binding']['sha256']==sha(entries['search']),'Confirmation selection binding differs')
    tasks=calibration['tasks']+selection['population_results']+selection['baseline_results']+confirm['tasks']
    hardware=read(entries['hardware']); verify_hardware(hardware)
    tasks+=hardware['results']+hardware['descendants']+[hardware['cpu_resume']]
    raw_procedure=read(entries['procedure-check']); verify_procedure(raw_procedure)
    reconciled_path=evidence('selection-reconciliation')
    require(source_closure(reconciled_path.parent)['passed'],'Selection reconciliation incomplete')
    from .reconciliation import verify_reconciliation
    reconciliation=read(reconciled_path); verify_reconciliation(reconciliation)
    procedure=read(ROOT/reconciliation['corrected_procedure']['path']); tasks+=verify_procedure(procedure)
    checked=[verify_task(d) for d in tasks]
    for method in ('bgpbt','baseline'):
        records=[read(Path(d)/'result.json') for d in confirm['tasks'] if Path(d).name.startswith(method+'-')]
        require([r['task']['seed'] for r in records]==[801,802,803],'Fresh seed roster differs')
        require(all(r['task']['kind']=='fresh' and 'input' not in r['task'] and
                    r['task']['config']==selection['selected'][method]['config'] for r in records),
                'Confirmation not fresh selected static configuration')
        require([r['score']['cost'] for r in records]==confirm['costs'][method],'Confirmation cost differs')
    negatives=[]
    def reject(name,fn):
        try: fn()
        except ValueError: negatives.append(name)
        else: raise ValueError('False evidence accepted: '+name)
    bad=deepcopy(selection); bad['work']['bgpbt']['transitions']-=1
    reject('omitted_work',lambda:verify_selection(bad))
    bad2=deepcopy(selection); bad2['global_optimum']=True
    reject('false_global_optimum',lambda:verify_selection(bad2))
    bad3=deepcopy(selection); bad3['selected']['bgpbt']['cost']=0.
    reject('false_selection',lambda:verify_selection(bad3))
    bad4=read(Path(tasks[0])/'result.json'); bad4['score']['cost']=0.
    reject('false_score',lambda:verify_task(tasks[0],bad4))
    reject('missing_hardware',lambda:verify_hardware({'passed':False}))
    bad5=deepcopy(procedure); bad5['estimand']='fresh_training_of_final_static_config'
    reject('static_as_procedure',lambda:verify_procedure(bad5))
    bad6=read(procedure['studies'][0]); bad6['selected']['bgpbt']['cost']=0.
    reject('false_repaired_winner',lambda:verify_selection_v2(bad6))
    bad7=read(procedure['studies'][0]); bad7['population_results']=bad7['population_results'][:-1]
    reject('omitted_candidate_work',lambda:verify_selection_v2(bad7))
    all_operations=[source_closure(p.parent) for p in sorted(BASE.glob('*-*/receipt.json')) if p.parent!=out]
    training_total={k:sum(r.get('charged_work',{}).get(k,0) for r in all_operations)
                    for k in ('transitions','sac_updates','distillation_updates')}
    result={'passed':True,'core_source':CORE,'tasks_reconstructed':len(checked),'scores':checked,
        'oracle':oracle_report(),'selected':selection['selected'],'confirmation':confirm,
        'hardware':hardware,'procedure':procedure,'negative_controls':negatives,'all_attempts_work':training_total,
        'failures_retained':[r['directory'] for r in all_operations if not r['passed']],
        'claims':{'companion_integration':True,'cpu_parallel':True,'gpu_parallel':True,
                  'global_optimality':False,'universal_learning_reliability':False}}
    write(out/'audit-result.json',result)


def master_audit(out):
    from .operations import evidence
    from tools.source_identity import source_digest
    from tools.program_continuation import continuation
    from tools.gap_trace import validate as validate_gaps
    audit_path=evidence('audit'); require(read(audit_path)['passed'],'Extension audit incomplete')
    require(source_digest(ROOT)==CORE,'Accepted core changed')
    p=read(ROOT/'docs/program/program.json'); candidate=deepcopy(p)
    for stage in candidate['continuation']['steps']:
        if stage['id']=='GAP-01/FINAL-AUDIT': stage['state']='complete'
        require(stage['state']=='complete','Incomplete master stage: '+stage['id'])
    for w in candidate['work_items']:
        if w['id']=='GAP-01': w['state']='complete'
        require(w['state']=='complete','Incomplete master work: '+w['id'])
    candidate['active_work_item']=None
    validate_gaps(read(ROOT/'docs/program/gap_closure.json'),candidate,ROOT,final=True)
    require(continuation(candidate)['master_complete'],'Master still incomplete')
    write(out/'master-audit-result.json',{'passed':True,'core_source':CORE,'work_items':len(candidate['work_items']),
        'stages':len(candidate['continuation']['steps']),'extension_audit':sha(audit_path),
        'original_gap_trace_valid':True,'global_optimum_claim':False})
