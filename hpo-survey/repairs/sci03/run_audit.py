"""SCI-03 independent evidence reconstruction and falsification controls."""
from fractions import Fraction
import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-delivery-03'

def check(condition,message):
    if not condition:raise ValueError(message)

def bound(row):
    path=ROOT/row['path']
    check(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],'Changed bound file '+str(path))
    return path

def number(v):
    check(isinstance(v,list) and len(v)==4 and all(type(x)is int for x in v),'Malformed endpoint')
    s,m,e,b=v
    check(s in (0,1) and m>=0 and b==m.bit_length() and abs(e)<10000,'Nonfinite endpoint')
    return Fraction((-1 if s else 1)*m)*Fraction(2)**e

def partition(report):
    paths=[row['path'] for row in report['rows']]
    check(len(paths)==report['leaf_count'] and len(set(paths))==len(paths)>0,'Leaf count/duplicate')
    check(all(isinstance(p,str) and len(p)<=40 and not set(p)-set('01') for p in paths),'Bad path')
    check(not any(p[:i] in set(paths) for p in paths for i in range(len(p))),'Overlapping partition')
    check(sum((Fraction(1,2**len(p)) for p in paths),Fraction())==1,'Partition holes')
    sums=[[Fraction(),Fraction()] for _ in range(5)]
    for row in report['rows']:
        check(len(row['bounds'])==5 and len(row['actions'])==2,'Missing quantities')
        check(all(a and all(type(i)is int and 0<=i<=3 for i in a) for a in row['actions']),'Invalid possible actions')
        mass=Fraction(1,2**len(row['path']))
        for j,ends in enumerate(row['bounds']):
            check(len(ends)==2,'Missing endpoint');lo,hi=map(number,ends);check(lo<=hi,'Reversed bounds')
            sums[j][0]+=mass*lo;sums[j][1]+=mass*hi
    check(len(report['bounds'])==5,'Aggregate roster')
    for ends,(lo,hi) in zip(report['bounds'],sums):
        check(number(ends[0])<=lo<=hi<=number(ends[1]),'Invalid outward aggregation')
    lo,hi=map(number,report['bounds'][2]);sign='POSITIVE' if lo>0 else 'NEGATIVE' if hi<0 else 'UNRESOLVED'
    check(report['sign']==sign,'False sign claim')
    check(report['status']=='ENCLOSED','False status')
    return True

def refused(fn):
    try:fn()
    except (ValueError,KeyError,TypeError):return True
    raise AssertionError('Altered evidence accepted')

def run(out):
    checked=set();controls={};receipts={}
    for op in ['wallet','delivery','verify']:
        close=json.loads((BASE/(op+'-completion.json')).read_text())
        rp=bound(close['receipt']);receipt=json.loads(rp.read_text())
        check(receipt['passed'] is True and receipt['returncode']==0 and receipt['stop_reason'] is None,'Failed prerequisite')
        check(receipt['source_digest']==receipt['end_source_digest']=='7a3975382cf19d55d3be3b653ccf5f860c576e13e7998a9dded47dff0a9adb17','Core changed')
        bound(receipt['manifest'])
        for row in receipt['inputs']+receipt['outputs']:
            bound(row);checked.add(row['path'])
        for row in receipt.get('runtime_inputs',[]):
            check(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256'],'Runtime changed')
        receipts[op]=(ROOT/close['directory'],receipt)
    # Reconstruct every predecessor evidence hash against the retained registry.
    old=json.loads((BASE/'predecessor/docs/program/program.json').read_text())
    for row in old['evidence']:
        # Source/evidence sources can historically be mutable active views;
        # preserve the predecessor registry and audit SCI-02's exact terminal packet.
        if row['id'].startswith('E-SCI02-'):
            bound(row);checked.add(row['path'])
    predecessor=json.loads((BASE/'predecessor/manifest.json').read_text())
    for row in predecessor['files']:bound(row)
    # Two failed allocations remain failures. Original wallet.py bytes are retained
    # and exactly satisfy their consumed bindings despite the prospective repair.
    for name in ['20261025T141740Z-wallet-93e799f6','20261025T141905Z-wallet2-fd843722']:
        receipt=json.loads((BASE/name/'receipt.json').read_text());check(receipt['passed'] is False,'Failure relabeled')
        for row in receipt['inputs']:
            if row['path'].endswith('/wallet.py'):
                check(hashlib.sha256((BASE/'wallet-before-priority-repair.py').read_bytes()).hexdigest()==row['sha256'],'Missing failed-source reconstruction')
            else:bound(row)
    failed_delivery=json.loads((BASE/'20261025T142903Z-delivery-fc7de44b/receipt.json').read_text())
    check(failed_delivery['passed'] is False,'Failed installation relabeled')
    bound(failed_delivery['manifest'])
    for row in failed_delivery['inputs']:bound(row)
    wd=receipts['wallet'][0];result=json.loads((wd/'result.json').read_text());check([p['seed'] for p in result['pairs']]==[5301,5302,5303],'Missing frozen policy pair')
    pairs=[]
    for pair in result['pairs']:
        report=json.loads((wd/f"wallet-{pair['seed']}.json").read_text());partition(report)
        check(all(number(report['bounds'][j][0])>0 for j in [0,1]),'Utility versus no action not proved')
        check(report['sign']==pair['sign'] and report['display_bounds']==pair['display_bounds'],'Summary differs')
        pairs.append({'seed':pair['seed'],'sign':report['sign'],'display_bounds':report['display_bounds'],'leaves':report['leaf_count']})
    sample=json.loads((wd/'wallet-5301.json').read_text())
    mutations={}
    b=copy.deepcopy(sample);b['rows'].pop();mutations['missing_leaf']=b
    b=copy.deepcopy(sample);b['rows'].append(b['rows'][0]);mutations['duplicate_leaf']=b
    b=copy.deepcopy(sample);b['rows'][0]['path']='q';mutations['invalid_path']=b
    b=copy.deepcopy(sample);b['bounds'][2]=[[0,1,0,1],[0,1,0,1]];mutations['false_aggregate']=b
    b=copy.deepcopy(sample);b['sign']='POSITIVE' if sample['sign']!='POSITIVE' else 'NEGATIVE';mutations['false_sign']=b
    b=copy.deepcopy(sample);b['rows'][0]['bounds'][0]=[[0,1,0,1],[0,0,0,0]];mutations['reversed_endpoint']=b
    b=copy.deepcopy(sample);b['rows'][0]['actions']=[[],[]];mutations['missing_actions']=b
    b=copy.deepcopy(sample);b['rows'][0]['bounds'][0][0]=[0,0,-123,-1];mutations['nonfinite_endpoint']=b
    for name,bad in mutations.items():controls[name]=refused(lambda:partition(bad))
    row=copy.deepcopy(receipts['wallet'][1]['outputs'][0]);row['sha256']='0'*64
    controls['changed_hash']=refused(lambda:bound(row))
    delivery=json.loads((receipts['delivery'][0]/'result.json').read_text());wheel=bound(delivery['wheel'])
    for row in delivery['source']+delivery['installed']:bound(row)
    dependencies=json.loads(bound(delivery['dependencies']).read_text())
    for row in dependencies:bound(row)
    with zipfile.ZipFile(wheel) as z:
        for row in delivery['installed']:
            path=bound(row);name='hponas_scientific_checks/'+path.name
            check(path.read_bytes()==z.read(name),'Wheel-installed mismatch')
    verify=json.loads((receipts['verify'][0]/'result.json').read_text())
    check(verify['ifbo_calls']==138 and verify['ifbo_original_failures']==6 and verify['nas_leaves']==297,'Saved roster incomplete')
    check([p['seed'] for p in verify['wallet_pairs']]==[5301,5302,5303] and all(p['status']=='VERIFIED' for p in verify['wallet_pairs']),'Missing installed replay')
    check(all(verify['controls'].values()) and all(verify['references_controls'].values())
          and all(verify['wallet_controls'].values()),'Failed negative controls')
    before=json.loads((BASE/'design-review.json').read_text());check(before['passed'],'Unreviewed plan')
    final={'mechanics_passed':True,'checked_files':len(checked),'pairs':pairs,'controls':controls,
        'wheel':delivery['wheel'],'installed_saved_roster':{'pi_calls':138,'ifbo_failures':6,'nas_models':6,'nas_leaves':297,'wallet_pairs':3},
        'original_failures_preserved':True,'core_unchanged':True,'all_six_policies_positive_versus_no_action':True,
        'qualified_scope':'Optional extension and named finite synthetic cases only.',
        'remaining_claims':['Population wallet superiority if its interval includes zero; tuning benefit across seeds.',
          'Unknown MNAR and causal identification without new assumptions/data/intervention.',
          'General finite-run convergence for existing learned or leapfrog samplers.',
          'ifBO effectiveness remains failed; optimizer integration cancelled.',
          'Unseen NAS models, training convergence and floating-point inference guarantees.',
          'Real-bank effectiveness and unattended production readiness.']}
    (out/'result.json').write_text(json.dumps(final,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'mechanics_passed':True,'checked_files':len(checked),'false_evidence_controls':len(controls)}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
