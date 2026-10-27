"""Fixed NAS companion qualification: all saved leaves and independent jets."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import mpmath as mp
from nas_certificate import check_certificate, leaves_cover

ROOT = Path('/home/ubuntu/workspace/hponas')
OLD = ROOT/'docs/program/evidence/2026-10-25/scientific-gap-trace-01'
ANALYSIS = OLD/'20261025T074605Z-analysis-833abd77'


def reject(fn):
    try:
        fn()
    except (ValueError, TypeError):
        return True
    raise AssertionError('Invalid NAS input accepted')


def run(out):
    spec=importlib.util.spec_from_file_location('independent_flat_jet',ROOT/'hpo-survey/repairs/scientific_gap_analysis.py')
    independent=importlib.util.module_from_spec(spec);spec.loader.exec_module(independent)
    mp.mp.dps=60
    rows=[];controls={};maximum=0
    for seed in range(7401,7407):
        proof=json.loads((ANALYSIS/f'nas-domain-{seed}.json').read_text())
        model_path=ROOT/proof['source']['path']
        assert hashlib.sha256(model_path.read_bytes()).hexdigest()==proof['source']['sha256']
        model=json.loads(model_path.read_text())['model']
        paths=[row['path'] for row in proof['leaves']]
        result=check_certificate(model,paths)
        assert result['status']=='CERTIFIED' and result['checked_leaves']==len(paths)
        # Independently execute the retained flattened Hessian implementation.
        # It does not import the new checker or consume its bound values.
        layers=independent.prepared(model)
        for path in paths:
            ok,_=independent.domain_bound(layers,path)
            assert ok
        mx=max(float(mp.mpf(tuple(v))) for row in result['rows'] for v in row['upper_endpoint_mpf'])
        maximum=max(maximum,mx)
        (out/f'certificate-{seed}.json').write_text(json.dumps(result,indent=2)+'\n')
        rows.append({'seed':seed,'leaves':len(paths),'status':result['status'],
                     'independent_all_leaves_passed':True,'maximum_upper_ratio_display':mx})
        print(json.dumps(rows[-1]),flush=True)
        if seed==7401:
            controls['empty_partition']=reject(lambda:leaves_cover([]))
            controls['missing_leaf']=reject(lambda:leaves_cover(paths[:-1]))
            controls['duplicate_leaf']=reject(lambda:leaves_cover(paths+[paths[0]]))
            controls['overlap']=reject(lambda:leaves_cover(['','0']))
            controls['invalid_bit']=reject(lambda:leaves_cover(['q']))
            controls['excess_depth']=reject(lambda:leaves_cover(['0'*25]))
            for key in ['weight','bias']:
                bad=copy.deepcopy(model)
                if key=='weight':bad['layers'][0][key][0].pop()
                else:bad['layers'][0][key].pop()
                controls['ragged_'+key]=reject(lambda:check_certificate(bad,['']))
            bad=copy.deepcopy(model);bad['layers'][0]['weight'][0][0]=float('nan')
            controls['nonfinite_weight']=reject(lambda:check_certificate(bad,['']))
            bad=copy.deepcopy(model);bad['config']['activation']='relu'
            controls['unsupported_activation']=reject(lambda:check_certificate(bad,['']))
            bad=copy.deepcopy(model);bad['config']['depth']=True
            controls['boolean_depth']=reject(lambda:check_certificate(bad,['']))
            controls['invalid_budget']=reject(lambda:check_certificate(model,paths,seconds=float('nan')))
            exhausted=check_certificate(model,paths,seconds=0)
            controls['resource_exhaustion_unverified']=exhausted['status']=='NOT_VERIFIED' and exhausted['checked_leaves']==0
            zero=copy.deepcopy(model)
            for layer in zero['layers']:
                layer['weight']=[[0. for _ in w] for w in layer['weight']]
                layer['bias']=[0. for _ in layer['bias']]
            failed=check_certificate(zero,[''])
            controls['zero_network_unverified']=failed['status']=='NOT_VERIFIED'
            assert all(controls.values())
    assert len(rows)==6
    result={'mechanics_passed':True,'scientific_status':'optional_companion_certified_for_six_saved_networks',
            'models':rows,'controls':controls,'maximum_upper_ratio_display':maximum,
            'new_fits':0,'source_qualification':'Manifest-bound companion only; not wheel/core qualification',
            'limitations':['Two-hidden-layer width-four SiLU and fixed target/domain/limits only.',
                           'Mathematical exact saved constants; not inference rounding or training convergence.',
                           'NOT_VERIFIED is not a proof of a violating point.']}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    run(Path(sys.argv[1]))
