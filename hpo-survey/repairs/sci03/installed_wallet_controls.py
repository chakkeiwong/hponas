"""Fixed SCI-03 wallet enclosure, analytic controls and independent diagnostics."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import mpmath as mp
import numpy as np

ROOT=Path('/home/ubuntu/workspace/hponas')
from hponas_scientific_checks import wallet as w
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-delivery-03'
FROZEN=ROOT/'docs/program/evidence/2026-10-25/scientific-gap-repair-02/wallet-frozen-policies.json'

def dump(path,x):path.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def rejected(fn):
    try:fn()
    except (ValueError,TypeError,ArithmeticError):return True
    raise AssertionError('Invalid input accepted')

def controls():
    mp.mp.dps=80
    rows=[]
    for z in [-20,-9,-8,-4,-1,-.01,0,.01,1,4,8,9,20]:
        enclosure=w.cdf(w.exact(z))
        expected=(1+mp.erf(mp.mpf(z)/mp.sqrt(2)))/2
        lo,hi=[mp.mpf(tuple(v)) for v in enclosure._mpi_]
        assert lo<=expected<=hi
        rows.append({'z':z,'bounds':w.endpoints(enclosure)})
    c={'mean':'intercept','scale':'constant','incidence':'censored','ridge':0.}
    low={'config':c,'theta':[-5.,-2.]};high={'config':c,'theta':[5.,-2.]}
    # Constant extreme policies have exact known actions on the whole domain.
    v,actions=w.cell([w.validate_model(low),w.validate_model(high)],'')
    assert actions==[[0],[3]]
    same=w.enclose(high,high,max_leaves=1,seconds=1)
    assert same['bounds'][2]==w.endpoints(w.iv.mpf(0))
    assert w.verify_partition(high,high,same)['status']=='VERIFIED'
    cs={'holes':rejected(lambda:w.cover(['0'])),'duplicates':rejected(lambda:w.cover(['0','0','1'])),
        'overlap':rejected(lambda:w.cover(['','0'])),'bad_path':rejected(lambda:w.cover(['q'])),
        'nonfinite':rejected(lambda:w.validate_model({'config':c,'theta':[float('nan'),0.]})),
        'shape':rejected(lambda:w.validate_model({'config':c,'theta':[0.]})),
        'unsupported':rejected(lambda:w.validate_model({'config':{'mean':'neural'},'theta':[]})),
        'resource':rejected(lambda:w.enclose(high,low,seconds=0)),
        'boolean_resource':rejected(lambda:w.enclose(high,low,max_leaves=True)),
        'range':rejected(lambda:w.validate_model({'config':c,'theta':[6.,0.]}))}
    bad=copy.deepcopy(same);bad['sign']='POSITIVE'
    cs['altered_sign']=rejected(lambda:w.verify_partition(high,high,bad))
    bad=copy.deepcopy(same);bad['rows'][0]['actions']=[[0],[0]]
    cs['altered_actions']=rejected(lambda:w.verify_partition(high,high,bad))
    bad=copy.deepcopy(same);bad['bounds'][2]=bad['bounds'][0]
    cs['altered_aggregate']=rejected(lambda:w.verify_partition(high,high,bad))
    return {'cdf_reference_points':rows,'known_actions':actions,'identical_policy_difference_exact_zero':True,'negative_controls':cs}

def run(out):
    ctrl=controls();dump(out/'controls.json',ctrl)
    spec=importlib.util.spec_from_file_location('original_wallet',ROOT/'hpo-survey/investigations/wallet_model.py')
    ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
    rows=[]
    for pair in json.loads(FROZEN.read_text())['pairs']:
        models=[]
        for role in ['selected','likelihood']:
            source=pair['policies'][role];path=ROOT/source['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
            models.append(json.loads(path.read_text())['model'])
        report=w.enclose(*models,max_leaves=2048,seconds=145)
        dump(out/f"wallet-{pair['seed']}.json",report)
        # Independent original float64 quadrature, diagnostic only.
        x,weights=ref.covariate_rule(96)
        true=np.column_stack([np.zeros(len(x))]+[ref.capped_mean(ref.truth(x),cap)-fee for cap,fee in zip(ref.CAPS,ref.FEES)])
        values=[]
        for model in models:
            parts=ref.parameters(np.array(model['theta']),x,model['config'])
            u=np.column_stack([np.zeros(len(x))]+[ref.capped_mean(parts,cap)-fee for cap,fee in zip(ref.CAPS,ref.FEES)])
            values.append(true[np.arange(len(x)),u.argmax(1)])
        diagnostic=[float(weights@v) for v in values]
        diagnostic += [float(weights@(values[0]-values[1]))]
        diagnostic += [float(weights@(true.max(1)-v)) for v in values]
        # Pointwise probes should be inside the outward true-utility rectangles.
        prepared=[w.validate_model(m) for m in models]
        for path in ['00000000','01010101','10101010','11111111']:
            bounds,_=w.cell(prepared,path)
            a,b,c,d=w.rectangle(path);pt=np.array([[float((a+b)/2),float((c+d)/2)]])
            tr=np.array([0.]+[float(ref.capped_mean(ref.truth(pt),cap)[0]-fee) for cap,fee in zip(ref.CAPS,ref.FEES)])
            for j,model in enumerate(models):
                par=ref.parameters(np.array(model['theta']),pt,model['config'])
                predicted=[0.]+[float(ref.capped_mean(par,cap)[0]-fee) for cap,fee in zip(ref.CAPS,ref.FEES)]
                val=tr[np.argmax(predicted)]
                assert float(bounds[j].a)-1e-12<=val<=float(bounds[j].b)+1e-12
        rows.append({'seed':pair['seed'],'sign':report['sign'],'display_bounds':report['display_bounds'],
                     'leaves':report['leaf_count'],'seconds':report['seconds'],'stop_reason':report['stop_reason'],
                     'quadrature_diagnostic_not_proof':diagnostic})
        print(json.dumps(rows[-1]),flush=True)
    dump(out/'result.json',{'mechanics_passed':True,'pairs':rows,'all_frozen_pairs_covered':len(rows)==3,
        'controls':ctrl,'new_observations':0,'new_fits':0,'scope':w.SCOPE,
        'scientific_status':'Certified conservative intervals; unresolved signs stay unresolved; not a universal tuning benefit.'})

if __name__=='__main__':run(Path(sys.argv[1]))
