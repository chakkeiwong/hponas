"""Auditable phase transitions; never rewrites completed attempt evidence."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-09'
EXT=ROOT/'extensions/rl-lqr-scale'
OPS=['engineering','actions','review','states','freeze','confirm','audit','master-audit']
def binding(path):
    p=Path(path);return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def refresh(p=None):
    if p is not None:save(ROOT/'docs/program/program.json',p)
    sys.path.insert(0,str(ROOT));from tools.program_state import validate,generated_documents
    errors,view=validate(ROOT)
    if errors:raise ValueError(errors)
    for name,text in generated_documents(ROOT,view).items():(ROOT/name).write_text(text)
def prepare(op):
    sys.path.insert(0,str(ROOT));from tools.source_identity import source_digest
    roster=[]
    for folder in [EXT/'hponas_rl_lqr_scale',EXT/'tests',ROOT/'extensions/rl-lqr-scalar/hponas_rl_lqr_scalar',ROOT/'extensions/rl-lqr5-bgpbt/hponas_rl_bgpbt',ROOT/'extensions/rl-lqr5/hponas_rl_lqr5']:
        roster.extend(sorted(folder.glob('*.py')))
    roster.extend([EXT/'run_operation.py',EXT/'control.py',ROOT/'program_operations/rl_lqr_ops.py',ROOT/'docs/program/LQR_DIMENSION_SCALING_2026_10_28.md',ROOT/'extensions/rl-lqr/runtime-lock.json'])
    for previous in OPS[:OPS.index(op)]:
        path=BASE/(previous+'-result.json')
        if path.exists():roster.append(path)
    limits={k:0 for k in ['transitions','sac_updates','distillation_updates','critic_updates','actor_updates']}
    counts={'engineering':(4096,1024,0,0,0),'actions':(196608,47616,0,0,0),'states':(196608,47616,0,0,0),'confirm':(589824,142848,0,0,0)}
    if op in counts:limits.update(zip(limits,counts[op]))
    seconds={'engineering':600,'actions':2400,'review':60,'states':3600,'freeze':60,'confirm':7200,'audit':1800,'master-audit':600}[op]
    manifest=dict(operation=op,review='Reviewed RL-LQR-09 phase; immutable predecessor, bounded work and separate scientific claims.',runner=binding(ROOT/'program_operations/lqr_scale_ops.py'),inputs=[binding(x) for x in roster],core_source=source_digest(ROOT),work_limits=limits,limits=dict(seconds=seconds,host_rss_bytes=16*1024**3,output_bytes=8*1024**3))
    path=BASE/(op+'-manifest.json')
    if path.exists():
        n=len(list(BASE.glob(op+'-manifest-predecessor-*.json')))+1;shutil.copyfile(path,BASE/(op+'-manifest-predecessor-'+str(n)+'.json'))
    save(path,manifest)
    p=json.loads((ROOT/'docs/program/program.json').read_text());w=next(w for w in p['work_items'] if w['id']=='RL-LQR-09')
    w['code_refs']=[str(x.relative_to(ROOT)) for x in sorted((EXT/'hponas_rl_lqr_scale').glob('*.py'))];w['test_refs']=[str(x.relative_to(ROOT)) for x in sorted((EXT/'tests').glob('*.py'))]
    refresh(p);print('Prepared',op,'sources',len(roster),'work',limits)
def finish(op):
    receipt=sorted(p for p in BASE.glob('*/receipt.json') if json.loads(p.read_text()).get('operation')==op)[-1];r=json.loads(receipt.read_text());assert r['passed'],r
    result=receipt.parent/(op+'-result.json');assert json.loads(result.read_text())['passed']
    target=BASE/(op+'-result.json');assert not target.exists();shutil.copyfile(result,target)
    p=json.loads((ROOT/'docs/program/program.json').read_text());archive=BASE/('before-finish-'+op+'.json');assert not archive.exists();shutil.copyfile(ROOT/'docs/program/program.json',archive)
    stage='GAP-01/FINAL-AUDIT' if op=='master-audit' else 'RL-LQR-09/'+op.upper();step=next(s for s in p['continuation']['steps'] if s['id']==stage);assert step['state']=='in_progress'
    w=next(w for w in p['work_items'] if w['id']==step['work_item'])
    for tag,path in [('RECEIPT',receipt),('RESULT',result)]:
        eid='E-RL-LQR09-'+op.upper()+'-'+tag;p['evidence'].append(dict(id=eid,kind='source_bound_'+op,**binding(path)));step['evidence_refs'].append(eid);w['evidence_refs'].append(eid)
    step['state']='complete';i=OPS.index(op);nxt=OPS[i+1] if i+1<len(OPS) else None
    if op=='audit':
        w['state']='complete';w['implementation']='verified';w['next_action']='Retain numerical outcomes and explicit unresolved convergence/generalization limits.'
        for req in p['requirements']:
            if req['id'].startswith('RL-LQR09-'):req['implementation_status']='Bounded repair and independent audit complete; numerical scientific outcomes govern claims.'
        p['active_work_item']='GAP-01';next(w for w in p['work_items'] if w['id']=='GAP-01')['state']='in_progress'
    elif op=='master-audit':w['state']='complete';w['implementation']='verified';w['next_action']='Expanded bounded repair reconciled; retain scientific limits.';p['active_work_item']=None
    else:w['next_action']='RL-LQR-09/'+nxt.upper()+': continue dependency-ordered bounded repair.'
    if nxt:
        ident='GAP-01/FINAL-AUDIT' if nxt=='master-audit' else 'RL-LQR-09/'+nxt.upper();next(s for s in p['continuation']['steps'] if s['id']==ident)['state']='in_progress'
    a,b=p['revision'].split('.');p['revision']=a+'.'+str(int(b)+1)
    m=ROOT/'CONSOLIDATED_MASTER_AUTHORITY.md';text=m.read_text();lines=text.splitlines();lines[2]='**Revision:** '+p['revision']+' — dimensional scaling '+op+' completed';text='\n'.join(lines)+'\n';a=text.index('**Current action:**');b=text.index('\n\n',a)
    current=('**Current action:** '+ident+' is active under the [reviewed dimensional scaling plan](docs/program/LQR_DIMENSION_SCALING_2026_10_28.md). Continue the bounded sequence; mathematical controls and model-informed gains do not establish generic SAC convergence.') if nxt else '**Current action:** RL-LQR-09 bounded dimensional studies and master reconciliation are complete. See the [repair results](extensions/rl-lqr-scale/RESULTS.md) for all outcomes and unresolved limits. No global neural optimum or general optimizer superiority is claimed.'
    m.write_text(text[:a]+current+text[b:]);refresh(p);print('Completed',stage,'next',nxt)
if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare(sys.argv[2])
    elif sys.argv[1]=='finish':finish(sys.argv[2])
    else:refresh()
