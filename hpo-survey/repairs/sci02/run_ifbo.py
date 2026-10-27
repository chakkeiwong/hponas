"""Fixed saved-tensor replay and independent upstream-body checks; no forwards."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import torch
from pi_float32 import PI_ATOL, probability_of_improvement
import ifbo_reference_v2 as ref

ROOT = Path('/home/ubuntu/workspace/hponas')
SAVED = ROOT/'validation/artifacts/V15a/20261008_finite_ifbo_01'
UPSTREAM = ROOT/'docs/program/evidence/2026-10-08/tier3-feasibility-01/reference-source/ifBO-421ff96986c8efbe92bd2ab64a4bab49b0dd46fb/src/PFNs4HPO/pfns4hpo/bar_distribution.py'


def rejected(fn):
    try:
        fn()
    except (ValueError, TypeError, AssertionError):
        return True
    raise AssertionError('Negative control unexpectedly accepted')


def run(out):
    torch.set_num_threads(1)
    tree = ast.parse(UPSTREAM.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BarDistribution')
    # Python uses the last definition. Do not accidentally test the earlier,
    # shadowed pi or the different FullSupportBarDistribution override.
    fn = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'pi'][-1]
    namespace = {'torch': torch}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(UPSTREAM), 'exec'), namespace)
    upstream = namespace['pi']
    rows, calls, controls = [], [], []
    for case in range(6):
        raw = json.loads((SAVED/f'raw-{case:02d}.json').read_text())
        rows.append(ref.verify_case(raw, SAVED/f'case-{case:02d}'))
        history = []
        for index, record in enumerate(raw['ifbo']['trace']):
            if index:
                rng = np.random.RandomState(42)
                for _ in range(index):
                    rng.uniform(-4, -1); rng.randint(1, 51)
                threshold = min(history)*(1-10**rng.uniform(-4, -1))
                path = SAVED/f'case-{case:02d}'/record['tensors']['path']
                assert hashlib.sha256(path.read_bytes()).hexdigest() == record['tensors']['sha256']
                with np.load(path, allow_pickle=False) as t:
                    logits, borders = t['logits'], t['borders']
                reconstructed = probability_of_improvement(logits, borders, threshold)
                # Source-traced MFPI creates a float32 incumbent tensor; PFN
                # subtracts it from one before passing it to BarDistribution.
                best = 1-torch.tensor([threshold], dtype=torch.float32)
                expected = upstream(SimpleNamespace(borders=torch.from_numpy(borders)),
                                    torch.from_numpy(logits), best).numpy()
                actual = np.asarray(record['probabilities'])
                assert np.max(np.abs(actual-expected)) <= PI_ATOL
                assert np.max(np.abs(actual-reconstructed)) <= PI_ATOL
                assert np.max(np.abs(expected-reconstructed)) <= PI_ATOL
                calls.append({'case':case,'index':index,'candidates':len(actual),
                              'upstream_saved_error':float(np.max(np.abs(actual-expected))),
                              'independent_saved_error':float(np.max(np.abs(actual-reconstructed))),
                              'independent_upstream_error':float(np.max(np.abs(expected-reconstructed)))})
            history.append(record['update']['loss'])
        if case == 0:
            bad = copy.deepcopy(raw);bad['ifbo']['trace'][1]['probabilities'][0] += .01
            controls.append(('altered_probability', rejected(lambda:ref.verify_case(bad,SAVED/'case-00'))))
            bad = copy.deepcopy(raw);bad['ifbo']['trace'][1]['queries'][0][1]['x'] += .01
            controls.append(('altered_query',rejected(lambda:ref.verify_case(bad,SAVED/'case-00'))))
            bad = copy.deepcopy(raw);bad['ifbo']['trace'][1]['tensors']['sha256'] = '0'*64
            controls.append(('altered_tensor_hash',rejected(lambda:ref.verify_case(bad,SAVED/'case-00'))))
    z=np.zeros((2,2),dtype=np.float32); b=np.array([0,.5,1],dtype=np.float32)
    for name,ln,bd,inc in [('dtype',z.astype(float),b,.3),('nan',z+np.nan,b,.3),
            ('width',z,np.array([0,0,1],dtype=np.float32),.3),('shape',z[:,:1],b,.3),
            ('incumbent',z,b,float('nan')),('empty',z[:0],b,.3),('boolean',z,b,True)]:
        controls.append((name,rejected(lambda:probability_of_improvement(ln,bd,inc))))
    assert np.array_equal(probability_of_improvement(z,b,1),[1,1])
    assert np.array_equal(probability_of_improvement(z,b,0),[0,0])
    assert len(calls)==138 and len(rows)==6 and not any(r['passes'] for r in rows)
    result={'mechanics_passed':True,'scientific_status':'saved_PI_conformance_repaired_performance_FAIL_preserved',
            'calls':calls,'cases':rows,'controls':dict(controls),'pi_atol':PI_ATOL,
            'maximum_error':max(c['independent_saved_error'] for c in calls),
            'maximum_upstream_saved_error':max(c['upstream_saved_error'] for c in calls),
            'new_training_updates':0,'new_pretrained_forwards':0,'original_FAIL_unchanged':True,
            'integration_cancelled':True,'complete_pretrained_identity_verified':False,
            'scope':'Saved tensors, float32 BarDistribution arithmetic and six traces only; no model-weight identity or general ifBO effectiveness claim.'}
    (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    run(Path(sys.argv[1]))
