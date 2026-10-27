"""Terminal SCI-02 source/evidence audit with false-completion controls."""
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-gap-repair-02'
RUNS={'ifbo':'20261025T102936Z-ifbo-cf145057',
      'nas':'20261025T103248Z-nas-3b548042',
      'references':'20261025T103621Z-references-61e810b0'}


def checked(binding):
    path=Path(binding['path'])
    if path.is_absolute() or '..' in path.parts or not (ROOT/path).resolve().is_relative_to(ROOT):
        raise ValueError('Evidence path escape')
    data=(ROOT/path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=binding['sha256']:
        raise ValueError('Bound evidence changed')
    return data


def check_result(op,result):
    if result.get('mechanics_passed') is not True or not result.get('controls') or not all(result['controls'].values()):
        raise ValueError('Failed/missing negative controls')
    if op=='ifbo':
        calls=result['calls'];cases=result['cases']
        if (len(calls)!=138 or {(c['case'],c['index']) for c in calls}!={(i,j) for i in range(6) for j in range(1,24)}
                or len(cases)!=6 or result['pi_atol']!=5e-6
                or any(not math.isfinite(c[k]) or not 0<=c[k]<=5e-6 for c in calls
                       for k in ('independent_saved_error','independent_upstream_error','upstream_saved_error'))
                or any(c['passes'] or c['gap']<=0 for c in cases)
                or not result['integration_cancelled'] or not result['original_FAIL_unchanged']
                or result['new_training_updates'] or result['new_pretrained_forwards']):
            raise ValueError('ifBO incomplete or original outcome changed')
    elif op=='nas':
        models=result['models']
        if (len(models)!=6 or {x['seed'] for x in models}!=set(range(7401,7407))
                or sum(x['leaves'] for x in models)!=297 or result['new_fits']
                or any(x['status']!='CERTIFIED' or not x['independent_all_leaves_passed'] for x in models)):
            raise ValueError('Incomplete NAS coverage')
    elif op=='references':
        if (result['new_observations'] or result['new_sampler_chains'] or result['new_fits']
                or result['wallet_superiority_established'] or result['existing_sampler_convergence_proved']
                or len(result['precision_curve'])!=9):
            raise ValueError('Unsupported reference claim or incomplete coverage')
    return True


def check_receipt(receipt,manifest,directory):
    if (receipt.get('passed') is not True or receipt.get('returncode')!=0
            or receipt.get('stop_reason') is not None or receipt.get('remaining_owned_pids')!=[]
            or receipt.get('inputs_unchanged') is not True
            or receipt['source_digest']!=receipt['end_source_digest']
            or receipt['source_digest']!=manifest['source_digest']
            or receipt['inputs']!=manifest['inputs']
            or receipt['runtime_inputs']!=manifest['runtime_inputs']):
        raise ValueError('Failed or inconsistent operation receipt')
    expected={str(p.relative_to(ROOT)) for p in directory.rglob('*') if p.is_file()
              and p.name not in ('receipt.json','intent.json','process.json','progress.json')}
    paths=[b['path'] for b in receipt['outputs']]
    if len(paths)!=len(set(paths)) or set(paths)!=expected or str((directory/'result.json').relative_to(ROOT)) not in paths:
        raise ValueError('Missing or duplicate operation outputs')
    return True


def reject(fn):
    try:fn()
    except (ValueError,KeyError,TypeError):return True
    raise AssertionError('False evidence accepted')


def run(out):
    operations=[];results={};controls={};checked_files=set()
    for op,directory in RUNS.items():
        receipt=json.loads((BASE/directory/'receipt.json').read_text())
        manifest=json.loads(checked(receipt['manifest']))
        check_receipt(receipt,manifest,BASE/directory)
        bad_receipt=copy.deepcopy(receipt);bad_receipt['outputs']=[]
        controls[op+'_missing_outputs']=reject(lambda:check_receipt(bad_receipt,manifest,BASE/directory))
        for binding in receipt['inputs']+receipt['outputs']:
            checked(binding);checked_files.add(binding['path'])
        for binding in manifest['runtime_inputs']:
            assert hashlib.sha256(Path(binding['path']).read_bytes()).hexdigest()==binding['sha256']
        for binding in manifest.get('prerequisites',[]):
            assert json.loads(checked(binding))['passed']
        result=json.loads((BASE/directory/'result.json').read_text());check_result(op,result);results[op]=result
        operations.append({'operation':op,'passed':True,'seconds':receipt['seconds'],'inputs':len(receipt['inputs'])})
        bad=copy.deepcopy(result);bad['mechanics_passed']=False
        controls[op+'_failed_mechanics']=reject(lambda:check_result(op,bad))
        bad=copy.deepcopy(result);bad['controls']={}
        controls[op+'_empty_controls']=reject(lambda:check_result(op,bad))
    for name,op,mutate in [
        ('missing_call','ifbo',lambda x:x['calls'].pop()),
        ('relaxed_tolerance','ifbo',lambda x:x.update(pi_atol=1e-4)),
        ('nonfinite_error','ifbo',lambda x:x['calls'][0].update(independent_saved_error=float('nan'))),
        ('performance_relabel','ifbo',lambda x:x['cases'][0].update(passes=True)),
        ('uncancelled_integration','ifbo',lambda x:x.update(integration_cancelled=False)),
        ('missing_network','nas',lambda x:x['models'].pop()),
        ('wallet_false_success','references',lambda x:x.update(wallet_superiority_established=True)),
        ('false_convergence','references',lambda x:x.update(existing_sampler_convergence_proved=True)),
        ('undeclared_observations','references',lambda x:x.update(new_observations=1))]:
        bad=copy.deepcopy(results[op]);mutate(bad);controls[name]=reject(lambda:check_result(op,bad))
    controls['altered_hash']=reject(lambda:checked({'path':str((BASE/'ifbo-manifest.json').relative_to(ROOT)),'sha256':'0'*64}))
    controls['path_escape']=reject(lambda:checked({'path':'../outside','sha256':'0'*64}))
    # Independently check coverage and exact serialized outward upper endpoints.
    leaf_count=0
    for seed in range(7401,7407):
        certificate=json.loads((BASE/RUNS['nas']/f'certificate-{seed}.json').read_text())
        rows=certificate['rows'];paths=[r['path'] for r in rows]
        assert len(paths)==len(set(paths)) and all(set(p)<=set('01') for p in paths)
        assert all(not (p!=q and q.startswith(p)) for p in paths for q in paths)
        assert sum((Fraction(1,2**len(p)) for p in paths),Fraction())==1
        for row in rows:
            assert row['proved'] is True
            for sign,mantissa,exponent,bitcount in row['upper_endpoint_mpf']:
                assert sign==0 and mantissa>=0 and bitcount==mantissa.bit_length()
                assert Fraction(mantissa)*Fraction(2)**exponent<=1
        assert certificate['checked_leaves']==certificate['total_leaves']==len(rows)
        leaf_count+=len(rows)
    assert leaf_count==297
    # Replay the six reported physical objectives analytically without calling
    # the companion or original training implementation.
    for i,row in enumerate(results['ifbo']['cases']):
        raw=json.loads((ROOT/f'validation/artifacts/V15a/20261008_finite_ifbo_01/raw-{i:02d}.json').read_text())
        a,b=raw['slot']['initial'];denom=a*a+b*b
        for arm,key in [('ifbo','ifbo_loss'),('asha','asha_loss')]:
            x=raw[arm]['certification'][-1]['x'];eta=1/40+3*x/5
            loss=(a*a*(1-eta)**16+b*b*(1-3*eta)**16)/denom
            assert abs(loss-row[key])<=2e-12+2e-10*abs(loss)
    provenance=json.loads((BASE/'provenance-repair.json').read_text())
    recovered=checked(provenance['old_wrapper']);current=checked(provenance['current_wrapper'])
    assert recovered.replace(b"OPS={'analysis':'ANALYSIS'}",b"OPS={'analysis':'ANALYSIS','review':'ANALYSIS'}")==current
    old_analysis=json.loads(checked(provenance['analysis_manifest']))
    for binding in old_analysis['inputs']:
        if binding['path']=='program_operations/scientific_gap_trace.py':
            assert hashlib.sha256(recovered).hexdigest()==binding['sha256']
        else:checked(binding)
    for row in json.loads((BASE/'predecessor/manifest.json').read_text())['files']:checked(row)
    frozen=json.loads((BASE/'wallet-frozen-policies.json').read_text())
    assert len(frozen['pairs'])==3 and frozen['new_observations']==0
    for pair in frozen['pairs']:
        checked(pair['summary'])
        for policy in pair['policies'].values():checked(policy)
    spec=importlib.util.spec_from_file_location('identity',ROOT/'tools/source_identity.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    digest=mod.source_digest(ROOT)
    assert digest=='7a3975382cf19d55d3be3b653ccf5f860c576e13e7998a9dded47dff0a9adb17'
    result={'mechanics_passed':True,'scientific_status':'bounded_companion_repairs_audited_with_explicit_unresolved_claims',
            'operations':operations,'unique_bound_files_checked':len(checked_files),'nas_leaves':leaf_count,
            'controls':controls,'qualified_core_unchanged':digest,'provenance_recovery_verified':True,
            'original_ifbo_performance_FAIL_preserved':True,'new_fits':0,'new_observations':0,'new_chains':0,
            'companion_packaged_in_wheel':False,'unresolved_claims':[
                'wallet superiority and useful population precision',
                'unknown MNAR and causal identification without assumptions/intervention',
                'existing leapfrog or arbitrary learned-map finite-run convergence',
                'ifBO recommendation performance and cancelled integration',
                'NAS unseen seeds, training convergence, floating-point inference and broader architectures',
                'real-bank effectiveness and unattended production readiness']}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':run(Path(sys.argv[1]))
