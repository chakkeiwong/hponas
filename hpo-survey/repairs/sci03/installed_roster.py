"""Fixed tests run with isolated installed Python outside the repository."""
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from hponas_scientific_checks import ifbo_reference,pi_float32,nas_certificate,wallet

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-delivery-03'
SCI02=ROOT/'docs/program/evidence/2026-10-25/scientific-gap-repair-02'
SAVED=ROOT/'validation/artifacts/V15a/20261008_finite_ifbo_01'

def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def reject(fn):
    try:fn()
    except (ValueError,TypeError):return True
    raise AssertionError('False input accepted')

def fraction(t):
    sign,mantissa,exponent,bits=t
    assert sign in (0,1) and type(mantissa)is int and mantissa>=0 and bits==mantissa.bit_length()
    return Fraction((-1 if sign else 1)*mantissa)*Fraction(2)**exponent

def main(out):
    assert not Path.cwd().is_relative_to(ROOT)
    for mod in [ifbo_reference,pi_float32,nas_certificate,wallet]:
        assert Path(mod.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    controls={};cases=[];count=0;maximum=0
    for i in range(6):
        raw=json.loads((SAVED/f'raw-{i:02d}.json').read_text())
        cases.append(ifbo_reference.verify_case(raw,SAVED/f'case-{i:02d}'))
        history=[]
        for index,row in enumerate(raw['ifbo']['trace']):
            if index:
                rng=np.random.RandomState(42)
                for _ in range(index):rng.uniform(-4,-1);rng.randint(1,51)
                threshold=min(history)*(1-10**rng.uniform(-4,-1))
                tpath=SAVED/f'case-{i:02d}'/row['tensors']['path']
                assert hashlib.sha256(tpath.read_bytes()).hexdigest()==row['tensors']['sha256']
                with np.load(tpath,allow_pickle=False) as t:p=pi_float32.probability_of_improvement(t['logits'],t['borders'],threshold)
                err=float(np.max(np.abs(p-np.array(row['probabilities']))));maximum=max(maximum,err);count+=1
                assert err<=5e-6
            history.append(row['update']['loss'])
        if i==0:
            bad=copy.deepcopy(raw);bad['ifbo']['trace'][1]['probabilities'][0]+=.01
            controls['ifbo_probability']=reject(lambda:ifbo_reference.verify_case(bad,SAVED/'case-00'))
            bad=copy.deepcopy(raw);bad['ifbo']['trace'][1]['tensors']['sha256']='0'*64
            controls['ifbo_tensor']=reject(lambda:ifbo_reference.verify_case(bad,SAVED/'case-00'))
            bad=copy.deepcopy(raw);bad['ifbo']['trace'][1]['queries'][0][1]['x']+=.01
            controls['ifbo_query']=reject(lambda:ifbo_reference.verify_case(bad,SAVED/'case-00'))
    assert count==138 and len(cases)==6 and not any(c['passes'] for c in cases)
    z=np.zeros((2,2),dtype=np.float32);b=np.array([0,.5,1],dtype=np.float32)
    for name,ln,bd,inc in [('dtype',z.astype(float),b,.3),('nan',z+np.nan,b,.3),('width',z,np.array([0,0,1],dtype=np.float32),.3),('shape',z[:,:1],b,.3),('incumbent',z,b,float('nan')),('empty',z[:0],b,.3),('boolean',z,b,True)]:
        controls['pi_'+name]=reject(lambda:pi_float32.probability_of_improvement(ln,bd,inc))
    dump(out/'installed-ifbo.json',{'calls':count,'cases':cases,'maximum_error':maximum,'controls':controls.copy(),'integration_cancelled':True})
    print('Installed PI: 138 calls, six retained FAILs',flush=True)
    # Saved independent SCI-02 certificates were also verified by a distinct
    # flattened-Hessian derivation. Here recompute every installed endpoint.
    models=[]
    for seed in range(7401,7407):
        old=json.loads((ROOT/f'docs/program/evidence/2026-10-25/scientific-gap-trace-01/20261025T074605Z-analysis-833abd77/nas-domain-{seed}.json').read_text())
        source=ROOT/old['source']['path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==old['source']['sha256']
        model=json.loads(source.read_text())['model'];paths=[x['path'] for x in old['leaves']]
        result=nas_certificate.check_certificate(model,paths)
        baseline=json.loads((SCI02/f'20261025T103248Z-nas-3b548042/certificate-{seed}.json').read_text())
        assert result['status']=='CERTIFIED' and result['rows']==baseline['rows']
        dump(out/f'installed-nas-{seed}.json',result)
        models.append({'seed':seed,'leaves':len(paths),'all_endpoints_match_independently_verified_predecessor':True})
        if seed==7401:
            for name,ps in [('empty',[]),('missing',paths[:-1]),('duplicate',paths+[paths[0]]),('overlap',['','0']),('bad_bit',['q']),('depth',['0'*25])]:
                controls['nas_'+name]=reject(lambda:nas_certificate.leaves_cover(ps))
            bad=copy.deepcopy(model);bad['layers'][0]['weight'][0].pop();controls['nas_ragged_weight']=reject(lambda:nas_certificate.check_certificate(bad,['']))
            bad=copy.deepcopy(model);bad['layers'][0]['bias'].pop();controls['nas_ragged_bias']=reject(lambda:nas_certificate.check_certificate(bad,['']))
            bad=copy.deepcopy(model);bad['layers'][0]['weight'][0][0]=float('nan');controls['nas_nan']=reject(lambda:nas_certificate.check_certificate(bad,['']))
            bad=copy.deepcopy(model);bad['config']['activation']='relu';controls['nas_activation']=reject(lambda:nas_certificate.check_certificate(bad,['']))
            bad=copy.deepcopy(model);bad['config']['depth']=True;controls['nas_boolean_depth']=reject(lambda:nas_certificate.check_certificate(bad,['']))
            controls['nas_bad_budget']=reject(lambda:nas_certificate.check_certificate(model,paths,seconds=float('nan')))
            controls['nas_resource']=nas_certificate.check_certificate(model,paths,seconds=0)['status']=='NOT_VERIFIED'
            bad=copy.deepcopy(model)
            for layer in bad['layers']:
                layer['weight']=[[0. for _ in row] for row in layer['weight']];layer['bias']=[0. for _ in layer['bias']]
            controls['nas_noncompliant']=nas_certificate.check_certificate(bad,[''])['status']=='NOT_VERIFIED'
        print(f'Installed NAS {seed}: {len(paths)} leaves',flush=True)
    spec=importlib.util.spec_from_file_location('installed_reference_tests',ROOT/'hpo-survey/repairs/sci03/installed_references.py')
    ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
    refs=out/'references';refs.mkdir();ref.run(refs)
    references=json.loads((refs/'result.json').read_text());assert references['mechanics_passed']
    spec=importlib.util.spec_from_file_location('installed_wallet_controls',ROOT/'hpo-survey/repairs/sci03/installed_wallet_controls.py')
    wc=importlib.util.module_from_spec(spec);spec.loader.exec_module(wc)
    wallet_controls=wc.controls();dump(out/'wallet-controls.json',wallet_controls)
    frozen=json.loads((SCI02/'wallet-frozen-policies.json').read_text())
    selected_result=json.loads((BASE/'wallet-completion.json').read_text())
    wallet_dir=ROOT/selected_result['directory'];pairs=[]
    for pair in frozen['pairs']:
        ms=[json.loads((ROOT/pair['policies'][role]['path']).read_text())['model'] for role in ['selected','likelihood']]
        report=json.loads((wallet_dir/f"wallet-{pair['seed']}.json").read_text())
        replay=wallet.verify_partition(*ms,report,seconds=180);assert replay['status']=='VERIFIED'
        # Independent exact rational aggregation; never use wallet.summarize.
        sums=[[Fraction(),Fraction()] for _ in range(5)]
        for row in report['rows']:
            mass=Fraction(1,2**len(row['path']))
            for j,endpoints in enumerate(row['bounds']):
                for k,endpoint in enumerate(endpoints):sums[j][k]+=mass*fraction(endpoint)
        for bounds,(lo,hi) in zip(report['bounds'],sums):
            assert fraction(bounds[0])<=lo<=hi<=fraction(bounds[1])
        pairs.append({'seed':pair['seed'],**replay,'exact_rational_aggregation_verified':True})
        print(f"Installed wallet {pair['seed']}: {replay['leaf_count']} leaves, {replay['sign']}",flush=True)
    assert all(controls.values())
    dump(out/'result.json',{'mechanics_passed':True,'installed_prefix':sys.prefix,'outside_cwd':str(Path.cwd()),
        'ifbo_calls':count,'ifbo_original_failures':6,'nas_models':models,'nas_leaves':sum(m['leaves'] for m in models),
        'wallet_pairs':pairs,'controls':controls,'references_controls':references['controls'],
        'wallet_controls':wallet_controls['negative_controls'],
        'new_fits':0,'new_observations':0,'scope':'Installed optional extension only; no general or real-bank effectiveness claim.'})

if __name__=='__main__':main(Path(sys.argv[1]))
