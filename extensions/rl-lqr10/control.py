"""Source-bound authority transitions for the bounded RL-LQR-04 extension."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'docs/program/evidence/2026-10-27/rl-lqr-04'
PLAN = 'docs/program/LQR10_H30_STUDY_2026_10_27.md'

def binding(path):
    path = Path(path)
    return {'path':str(path.relative_to(ROOT)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')

def register():
    BASE.mkdir(parents=True, exist_ok=True)
    archive = BASE/'admission'
    for name in ['CONSOLIDATED_MASTER_AUTHORITY.md', 'docs/program/program.json',
                 'docs/progress.md', 'TRACEABILITY_MATRIX_v1.md', 'docs/PROGRAM_OPERATIONS.md']:
        dest = archive/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists(): shutil.copyfile(ROOT/name, dest)
    p = json.loads((ROOT/'docs/program/program.json').read_text())
    if any(x['id']=='RL-LQR-04' for x in p['work_items']): return
    eid = 'E-RL-LQR04-PLAN'
    p['evidence'].append(dict(id=eid, kind='reviewed_plan', **binding(ROOT/PLAN)))
    p['source_inputs'].append(dict(id='S-RL-LQR04-PLAN', **binding(ROOT/PLAN)))
    p['decisions'].append(dict(id='D-RL-LQR04-20261027', title='Execute ten-state horizon-thirty joint SAC benchmark',
        status='accepted', authorization='User: try a higher dimension case, and test a 10 dimension case with time horizon = 30.',
        rationale='Extend the preceding joint actor/critic HPO/NAS benchmark with bounded work and scalable evaluation.',
        consequence='Register RL-LQR-04 and reopen final reconciliation; retain predecessor evidence.', evidence_refs=[eid]))
    p['work_items'].append(dict(id='RL-LQR-04', title='Ten-state horizon-thirty joint SAC BG-PBT study',
        phase='rl_lqr_extension', owner='Single inspector/editor', state='in_progress', implementation='partial',
        dependencies=['RL-LQR-03'], decision_dependencies=['D-RL-LQR04-20261027'], code_refs=[], test_refs=[],
        acceptance_campaigns=[], evidence_refs=[eid],
        done_when='Oracle, sampled regret evaluation, paired searches, holdout scores and independent audit complete with explicit outcomes.',
        next_action='RL-LQR-04/ENGINEERING: validate oracle, evaluation and learner before training.',
        budget=dict(cpu_cores=3, study_seconds=3600, scientific_transitions_max=466944,
                    sac_updates_max=115776, distillation_updates_max=768, owned_rss_bytes=16*1024**3, output_bytes=8*1024**3)))
    for ident,title in [('MODEL','Ten-state thirty-step attainable analytical reference'),
                        ('STUDY','Paired joint procedures and separate holdout scoring'),
                        ('AUDIT','Source, accounting and evidence reconstruction audit')]:
        p['requirements'].append(dict(id='RL-LQR04-'+ident,title=title,decision_ids=[],audit_findings=[],
            disposition='required',work_items=['RL-LQR-04'],sources=[PLAN],reason='User-authorized dimension and horizon extension.',
            implementation_status='In progress; no learning conclusion yet.'))
    prev='RL-LQR-03/AUDIT'
    for name,kind,action in [('CONTRACT','preparation','Freeze model, estimator, seeds and work'),
        ('ENGINEERING','preparation','Verify reference, sampler, learner dimensions, checkpoint isolation and selection'),
        ('STUDY','execution','Execute three paired joint searches and test frozen winners'),
        ('AUDIT','preparation','Independently reconstruct reference, scores, source, artifacts, work and limitations')]:
        ident='RL-LQR-04/'+name
        p['continuation']['steps'].insert(-1,dict(id=ident,work_item='RL-LQR-04',kind=kind,
            state='complete' if name=='CONTRACT' else 'in_progress' if name=='ENGINEERING' else 'planned',
            dependencies=[prev],action=action,done_when=action+'; preserve evidence and scientific limits.',
            evidence_refs=[eid] if name in ('CONTRACT','ENGINEERING') else []))
        prev=ident
    p['execution_contract']['work_completion_steps']['RL-LQR-04']=['RL-LQR-04/AUDIT']
    final=next(x for x in p['continuation']['steps'] if x['id']=='GAP-01/FINAL-AUDIT')
    final['state']='planned'; final['dependencies'].append('RL-LQR-04/AUDIT')
    gap=next(x for x in p['work_items'] if x['id']=='GAP-01')
    gap['state']='planned'; gap['next_action']='Reconcile RL-LQR-04 after its evidence audit.'
    p['revision']='2.686'; p['active_work_item']='RL-LQR-04'
    p['continuation']['scope']='Execute bounded RL-LQR-04 and terminal reconciliation; preserve prior scientific limits.'
    save(ROOT/'docs/program/program.json',p)
    m=ROOT/'CONSOLIDATED_MASTER_AUTHORITY.md'; text=m.read_text()
    text=text.replace('**Revision:** 2.685 — repaired joint tuning and shared GPUs audited; adopted bounded master complete',
                      '**Revision:** 2.686 — ten-state horizon-thirty extension admitted')
    start=text.index('**Current action:**'); end=text.index('\n\n',start)
    text=text[:start]+('**Current action:** RL-LQR-04/ENGINEERING is active under the '
        '[ten-state horizon-thirty plan](docs/program/LQR10_H30_STUDY_2026_10_27.md). '
        'Extend the one-action cyclic LQR and joint architecture/rate problem. Replace infeasible trillion-path '
        'enumeration with an exact analytical reference and explicitly sampled policy-regret evaluation. '
        'Three paired procedures and separate test scoring follow engineering validation. '
        'The expanded master is not complete; no claim of SAC convergence is implied.')+text[end:]
    m.write_text(text)
    print('Registered RL-LQR-04; predecessor preserved.')

def refresh():
    sys.path.insert(0,str(ROOT))
    from tools.program_state import validate,generated_documents
    errors,view=validate(ROOT)
    if errors:raise ValueError(errors)
    for name,text in generated_documents(ROOT,view).items():(ROOT/name).write_text(text)
    print('Refreshed master, progress and traceability')

def prepare(operation):
    sys.path.insert(0,str(ROOT))
    from tools.source_identity import source_digest
    roster=[]
    for directory in ('extensions/rl-lqr10/hponas_rl_lqr10','extensions/rl-lqr10/tests',
                      'extensions/rl-lqr5-bgpbt/hponas_rl_bgpbt','extensions/rl-lqr5/hponas_rl_lqr5'):
        roster.extend(sorted((ROOT/directory).glob('*.py')))
    roster.extend([ROOT/'extensions/rl-lqr10/run_operation.py',ROOT/'extensions/rl-lqr/runtime-lock.json',
                   ROOT/'program_operations/rl_lqr_ops.py',ROOT/PLAN])
    budgets={'engineering':dict(transitions=1024,sac_updates=256,distillation_updates=64),
             'study':dict(transitions=466944,sac_updates=115776,distillation_updates=768),
             'audit':dict(transitions=0,sac_updates=0,distillation_updates=0),
             'master-audit':dict(transitions=0,sac_updates=0,distillation_updates=0)}
    manifest=dict(operation=operation,review='Bounded predecessor extension; exact reference plus sampled validation/holdout.',
        runner=binding(ROOT/'program_operations/lqr10_ops.py'),inputs=[binding(x) for x in roster],
        core_source=source_digest(ROOT),work_limits=budgets[operation],
        limits=dict(seconds={'engineering':600,'study':3600,'audit':900,'master-audit':600}[operation],
                    host_rss_bytes=16*1024**3,output_bytes=8*1024**3))
    save(BASE/(operation+'-manifest.json'),manifest)
    p=json.loads((ROOT/'docs/program/program.json').read_text())
    w=next(x for x in p['work_items'] if x['id']=='RL-LQR-04')
    w['code_refs']=[str(x.relative_to(ROOT)) for x in sorted((ROOT/'extensions/rl-lqr10/hponas_rl_lqr10').glob('*.py'))]
    w['test_refs']=[str(x.relative_to(ROOT)) for x in sorted((ROOT/'extensions/rl-lqr10/tests').glob('*.py'))]
    save(ROOT/'docs/program/program.json',p)
    refresh();print('Prepared',operation,'with',len(roster),'source inputs')

def finish(operation):
    candidates=sorted(BASE.glob('*-'+operation+'-*/receipt.json'))
    if not candidates:raise ValueError('No operation receipt')
    receipt=candidates[-1];r=json.loads(receipt.read_text())
    if not r['passed']:raise ValueError('Latest operation did not pass')
    result=receipt.parent/(operation+'-result.json')
    if not result.exists():raise ValueError('Missing result')
    p=json.loads((ROOT/'docs/program/program.json').read_text())
    archive=BASE/('before-finish-'+operation);archive.mkdir(exist_ok=True)
    dest=archive/'program.json'
    if not dest.exists():shutil.copyfile(ROOT/'docs/program/program.json',dest)
    index_path=ROOT/'extensions/rl-lqr10/results-index.json'
    index=json.loads(index_path.read_text()) if index_path.exists() else {}
    index[operation]=binding(result);save(index_path,index)
    stage='GAP-01/FINAL-AUDIT' if operation=='master-audit' else 'RL-LQR-04/'+operation.upper()
    step=next(s for s in p['continuation']['steps'] if s['id']==stage)
    if step['state']!='in_progress':raise ValueError('Stage is not active')
    work=next(w for w in p['work_items'] if w['id']==step['work_item'])
    for suffix,path in [('RECEIPT',receipt),('RESULT',result)]:
        eid='E-RL-LQR04-'+operation.upper()+'-'+suffix
        if any(e['id']==eid for e in p['evidence']):raise ValueError('Evidence already registered')
        p['evidence'].append(dict(id=eid,kind='source_bound_'+operation,**binding(path)))
        step['evidence_refs'].append(eid);work['evidence_refs'].append(eid)
    step['state']='complete'
    next_op={'engineering':'study','study':'audit','audit':'master-audit','master-audit':None}[operation]
    if operation=='audit':
        work['state']='complete';work['implementation']='verified'
        work['next_action']='Retain all paired test outcomes; no convergence or global-optimality claim.'
        for req in p['requirements']:
            if req['id'].startswith('RL-LQR04-'):req['implementation_status']='Study and reconstruction verified; sampled gap and limited seed evidence remain explicit.'
        gap=next(w for w in p['work_items'] if w['id']=='GAP-01');gap['state']='in_progress'
        p['active_work_item']='GAP-01'
    elif operation=='master-audit':
        work['state']='complete';work['implementation']='verified';p['active_work_item']=None
        work['next_action']='Expanded bounded master reconciled; retain scientific non-convergence limits.'
    else:work['next_action']='RL-LQR-04/'+next_op.upper()+': continue reviewed bounded sequence.'
    if next_op:
        nxt='GAP-01/FINAL-AUDIT' if next_op=='master-audit' else 'RL-LQR-04/'+next_op.upper()
        next(s for s in p['continuation']['steps'] if s['id']==nxt)['state']='in_progress'
    major,minor=p['revision'].split('.');p['revision']=major+'.'+str(int(minor)+1)
    save(ROOT/'docs/program/program.json',p)
    m=ROOT/'CONSOLIDATED_MASTER_AUTHORITY.md';text=m.read_text();lines=text.splitlines()
    lines[2]='**Revision:** '+p['revision']+' — ten-state horizon-thirty '+('bounded study audited' if not next_op else operation+' completed')
    text='\n'.join(lines)+'\n';start=text.index('**Current action:**');end=text.index('\n\n',start)
    current=('**Current action:** '+('GAP-01/FINAL-AUDIT' if next_op=='master-audit' else 'RL-LQR-04/'+next_op.upper())+
        ' is active. Continue the [ten-state horizon-thirty program](docs/program/LQR10_H30_STUDY_2026_10_27.md). '
        'Predecessor evidence remains unchanged. Engineering completion does not establish SAC convergence.') if next_op else (
        '**Current action:** The bounded RL-LQR-04 experiment and final master reconciliation are complete. '
        'See the [ten-state result report](extensions/rl-lqr10/RESULTS.md) for analytical reference, all three paired '
        'holdout outcomes and uncertainty. This closes the requested experiment, not convergence to the optimum '
        'or general BG-PBT superiority. No scientific process remains active.')
    m.write_text(text[:start]+current+text[end:]);refresh()
    print('Completed',stage,'next',next_op)

if __name__=='__main__':
    if len(sys.argv)==1:register()
    elif sys.argv[1]=='prepare':prepare(sys.argv[2])
    elif sys.argv[1]=='finish':finish(sys.argv[2])
    elif sys.argv[1]=='refresh':refresh()
    else:raise ValueError('Unknown control operation')
