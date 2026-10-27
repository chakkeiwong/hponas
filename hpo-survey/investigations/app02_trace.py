"""Read-only APP-01 diagnosis: re-score saved fits; never train or select."""
from pathlib import Path
import hashlib
import itertools
import json
import math
import statistics
import sys
import numpy as np

ROOT = Path('/home/ubuntu/workspace/hponas')
sys.path.insert(0, str(ROOT / 'hpo-survey/applications'))
from references import close, net_numpy, policy_truth, enumerate_value

BASE = ROOT / 'docs/program/evidence/2026-10-24/app-01'
NAS = BASE / '20261024T130144Z-nas-8261839a/results'
TRANSPORT = BASE / '20261024T130543Z-transport-9e8c4466/results'
LIMITS = {'dx': .25 * .6 ** 2 * math.exp(.3),
          'da': .25 * .5 ** 2 * math.exp(.3)}

def read(path):
    return json.loads(Path(path).read_text())

def binding(path):
    return {'path': str(path.relative_to(ROOT)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False)

def payload(path):
    record = read(path)
    assert hashlib.sha256(canonical(record['payload']).encode()).hexdigest() == record['sha256']
    return record['payload']

def score(m, x):
    y, jac = net_numpy(m, x)
    target = np.exp(-x[:, 0] * x[:, 1])
    truth = np.column_stack((-x[:, 1] * target, -x[:, 0] * target))
    errors = np.abs(jac - truth)
    losses = np.mean(np.column_stack(((y - target) ** 2, errors ** 2)), axis=0)
    ratios = errors / np.array([LIMITS['dx'], LIMITS['da']])
    row, axis = np.unravel_index(np.argmax(ratios), ratios.shape)
    return {'loss': float(sum(losses)), 'losses': losses.tolist(),
            'dx_max': float(errors[:, 0].max()), 'da_max': float(errors[:, 1].max()),
            'feasible': bool(np.max(ratios) <= 1.), 'max_limit_ratio': float(np.max(ratios)),
            'worst_point': x[row].tolist(), 'worst_derivative': ('dx', 'da')[axis],
            'violating_points': int(np.sum(np.any(ratios > 1., axis=1)))}

def nas_diagnosis():
    mesh = np.array(list(itertools.product(np.linspace(-.5, .5, 41), np.linspace(.2, .6, 41))))
    reports = []; all_models = []; bindings = []
    for rep in (401, 502, 603):
        base = NAS / str(rep); records = read(base / 'data.json'); bindings.append(binding(base / 'data.json'))
        points = {role: np.array([r['x'] for key, r in records.items() if key.startswith(role + '_')])
                  for role in ('train', 'validation', 'final')}
        points['mesh'] = mesh; grid = read(base / 'grid.json'); configs = []; unique = {}
        for entry in grid['rows']:
            models = []
            for path in entry['artifacts']:
                path = Path(path); p = payload(path); bindings.append(binding(path))
                scores = {role: score(p['model'], x) for role, x in points.items()}
                close(scores['validation']['loss'], p['loss'])
                close(scores['validation']['dx_max'], p['metrics']['dx_max'])
                close(scores['validation']['da_max'], p['metrics']['da_max'])
                row = {'replicate': rep, 'config': p['physical'], 'seed': p['seed'], 'role': 'tuning',
                       'artifact': str(path.relative_to(ROOT)), 'scores': scores, 'curve': p['model']['curve']}
                models.append(row); all_models.append(row); unique[(canonical(p['config']), p['seed'])] = row
            configs.append({'config': models[0]['config'], 'mean_validation_loss': statistics.mean(m['scores']['validation']['loss'] for m in models),
                            'worst_validation_ratio': max(m['scores']['validation']['max_limit_ratio'] for m in models),
                            'both_validation_feasible': all(m['scores']['validation']['feasible'] for m in models),
                            'both_mesh_feasible': all(m['scores']['mesh']['feasible'] for m in models)})
        final_models = []; seen = set()
        for path in sorted(base.glob('*/models/*_final_*.json')):
            p = payload(path); key = (canonical(p['config']), p['seed'])
            if key in seen: continue
            seen.add(key); bindings.append(binding(path))
            evaluation_points = {**points, 'refit_train': np.concatenate((points['train'], points['validation']))}
            scores = {role: score(p['model'], x) for role, x in evaluation_points.items()}
            close(scores['final']['loss'], p['loss']);close(scores['final']['dx_max'], p['metrics']['dx_max']);close(scores['final']['da_max'], p['metrics']['da_max'])
            row = {'replicate': rep, 'config': p['physical'], 'seed': p['seed'], 'role': 'final',
                   'artifact': str(path.relative_to(ROOT)), 'scores': scores, 'curve': p['model']['curve']}
            final_models.append(row); all_models.append(row)
        closest = min(configs, key=lambda x: (x['worst_validation_ratio'], x['mean_validation_loss']))
        counts = {role: sum(m['scores'][role]['feasible'] for m in unique.values()) for role in points}
        reports.append({'replicate': rep, 'grid_settings': len(configs), 'grid_models': len(unique),
                        'individual_feasible_models': counts, 'joint_validation_feasible_settings': sum(c['both_validation_feasible'] for c in configs),
                        'joint_mesh_feasible_settings': sum(c['both_mesh_feasible'] for c in configs), 'closest_setting': closest,
                        'final_models': final_models, 'configs': configs})
    # exp(-a*x) cubic in t=a*x. |t| <= .3. Taylor's theorem bounds
    # value error by exp(.3)*.3^4/4!, and derivative errors by
    # max(a or |x|)*exp(.3)*.3^3/3!. This is an analytic comparator, not an MLP.
    polynomial = {'degree_in_ax': 3, 'value_bound': math.exp(.3) * .3 ** 4 / math.factorial(4),
                  'dx_bound': .6 * math.exp(.3) * .3 ** 3 / math.factorial(3),
                  'da_bound': .5 * math.exp(.3) * .3 ** 3 / math.factorial(3),
                  'scope': 'Uniform analytic target-attainability comparator; does not prove attainability for the frozen MLP class or optimizer.'}
    assert polynomial['dx_bound'] < LIMITS['dx'] and polynomial['da_bound'] < LIMITS['da']
    t=mesh[:,0]*mesh[:,1];poly=1-t+t*t/2-t*t*t/6
    dpoly=np.column_stack((-mesh[:,1]*(1-t+t*t/2),-mesh[:,0]*(1-t+t*t/2)))
    target=np.exp(-t);truth=np.column_stack((-mesh[:,1]*target,-mesh[:,0]*target))
    assert max(abs(poly-target)) <= polynomial['value_bound']
    assert max(abs(dpoly[:,0]-truth[:,0])) <= polynomial['dx_bound']
    assert max(abs(dpoly[:,1]-truth[:,1])) <= polynomial['da_bound']
    return {'limits':LIMITS,'mesh_points':len(mesh),'reports':reports,'model_rescores':all_models,
            'analytic_comparator':polynomial,'inputs':bindings,
            'interpretation':'Mesh is diagnostic only, not a uniform MLP certificate. Rescored final data is now exploratory and cannot validate future repairs.'}

def transport_trace():
    groups={};inputs=[]
    for path in sorted(TRANSPORT.glob('*/*/handoff.json')):
        h=read(path);inputs.append(binding(path))
        for c in h['candidates']:
            if c['status']!='verified':continue
            a=c['posterior']['assessment'];chains=c['posterior']['chains'];key=(c['step_size'],c['leapfrog_steps'])
            rows=groups.setdefault(key,[])
            rows.append({'mean_error':max(abs(x) for x in a['mean']),
                         'moment_error':max(abs(x-y) for x,y in zip(a['second_moment'],a['true_second_moment'])),
                         'acceptance':statistics.mean(float(r['accepted']) for chain in chains for r in chain['records'])})
    return {'groups':[{'step_size':h,'steps':length,'integration_time':h*length,
                      'mean_abs_mean_error':statistics.mean(r['mean_error'] for r in rows),
                      'max_abs_mean_error':max(r['mean_error'] for r in rows),
                      'mean_acceptance':statistics.mean(r['acceptance'] for r in rows)} for (h,length),rows in sorted(groups.items())],
            'inputs':inputs,'interpretation':'Post-hoc descriptive grouping, not a candidate-selection or convergence rule.'}

def policy_trace():
    p,r=policy_truth();v=np.zeros(3);acts=[];advantages=[]
    for _ in range(3):
        q=r+.95*(p@v);a=np.argmax(q,axis=1);acts.append(a.tolist());advantages.append((q[:,1]-q[:,0]).tolist());v=q[np.arange(3),a]
    acts=acts[::-1];advantages=advantages[::-1];initial=np.array([.25,.5,.25]);optimal=float(initial@v);close(enumerate_value(p,r,acts),optimal)
    class_rows=[]
    for threshold,slope in itertools.product((-1.5,-.5,.5,1.5),(0.,.3)):
        a=[[int(s>threshold+slope*t) for s in (-1.,0.,1.)] for t in range(3)]
        class_rows.append({'threshold':threshold,'time_slope':slope,'actions':a,'exact_value':enumerate_value(p,r,a)})
    # Independent finite path enumeration of every deterministic Markov policy.
    all_values=[enumerate_value(p,r,np.array(bits).reshape(3,3).tolist()) for bits in itertools.product((0,1),repeat=9)]
    close(max(all_values),optimal)
    return {'optimal_value':optimal,'optimal_actions':acts,'action1_minus_action0':advantages,
            'declared_class_best':max(r['exact_value'] for r in class_rows),'declared_class':class_rows,
            'all_markov_policies_enumerated':len(all_values),'optimal_in_class':any(row['actions']==acts for row in class_rows)}

def main(out):
    nas=nas_diagnosis();result={'passed':True,'stage':'APP-02/NAS-REPLAY','new_training_fits':0,
        'nas':nas,'transport_trace':transport_trace(),'policy_trace':policy_trace(),
        'limits':['Exploratory diagnosis of retained data, not new confirmation.','No scientific thresholds or source implementations changed.']}
    with (out/'diagnosis.json').open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps({'passed':True,'new_training_fits':0,'nas_models_rescored':len(nas['model_rescores']),
                      'grid_summary':[{k:r[k] for k in ('replicate','individual_feasible_models','joint_validation_feasible_settings','joint_mesh_feasible_settings')} for r in nas['reports']],
                      'policy_optimum':result['policy_trace']['optimal_actions']}),flush=True)

if __name__=='__main__':main(Path(sys.argv[1]))
