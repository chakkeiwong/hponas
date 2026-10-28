"""Independent reconstruction from portable actors, raw paths and Study state.

The checker deliberately does not call the training scorer or Riccati helper.
Its finite equations are written directly from the frozen mathematical contract.
"""
from fractions import Fraction as F
from itertools import product
import hashlib
import json
import math
from pathlib import Path
import pickle

import numpy as np
import torch


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference():
    p, c = F(1), F(0)
    gains, curvatures = [], []
    for _ in range(8):
        curvature = F(1, 10)+F(99, 100)*p
        gain = F(99, 100)*F(4, 5)*p/curvature
        c = F(99, 100)*(c+p/F(400))
        p = 1+F(99, 100)*F(16, 25)*p*F(1, 10)/curvature
        gains.append(gain); curvatures.append(curvature)
    return float(p+c), np.array(list(reversed(gains)), float), np.array(list(reversed(curvatures)), float)


def verify_paths(data, expected_cost, actor=None):
    states, actions, noise = (np.asarray(data[k]) for k in ('states', 'actions', 'noise'))
    require(states.shape == (512, 9) and actions.shape == noise.shape == (512, 8), 'Incomplete path shapes')
    require(all(np.isfinite(x).all() for x in (states, actions, noise)), 'Nonfinite paths')
    signs = np.array(list(product((-1., 1.), repeat=9)))
    require(np.array_equal(states[:, 0], signs[:, 0]), 'Initial law differs')
    require(np.array_equal(noise, signs[:, 1:]*.05), 'Noise law differs')
    require(np.max(np.abs(actions)) <= 1., 'Infeasible actions')
    require(np.allclose(states[:, 1:], .8*states[:, :-1]+actions+noise, rtol=0., atol=1e-14), 'Dynamics differ')
    if actor is not None:
        for t in range(8):
            obs = torch.tensor(np.column_stack([states[:, t], np.full(512, (8-t)/8)]), dtype=torch.float32)
            with torch.no_grad():
                computed = actor(obs).cpu().numpy().reshape(-1)
            require(np.array_equal(computed, actions[:, t]), 'Saved actor does not reproduce paths')
    discount = .99**np.arange(8)
    path_costs = ((states[:, :-1]**2+.1*actions**2)*discount).sum(axis=1)+.99**8*states[:, -1]**2
    optimum, gains, curvature = reference()
    advantage = ((actions+states[:, :-1]*gains)**2*curvature*discount).sum(axis=1)
    cost = math.fsum(path_costs)/512
    excess = math.fsum(advantage)/512
    tolerance = 256*8*np.finfo(float).eps*max(1., cost, excess)
    require(abs(cost-expected_cost) <= tolerance, 'Saved cost differs')
    require(abs(cost-optimum-excess) <= tolerance and cost >= optimum-tolerance, 'Optimality identity differs')
    require(np.max(np.abs(path_costs-data['path_costs'])) <= tolerance, 'Raw path costs differ')
    require(np.max(np.abs(advantage-data['path_advantages'])) <= tolerance, 'Raw path advantages differ')
    return {'cost': cost, 'optimal_cost': optimum, 'gap': cost-optimum,
            'identity_error': abs(cost-optimum-excess), 'paths': 512}


def verify_fit(path):
    path = Path(path)
    row = read(path/'fit-result.json')
    for key, name in (('actor', 'actor.pt'), ('paths', 'paths.npz')):
        require(row[key]['sha256'] == sha(path/name), 'Saved '+key+' bytes differ')
    with np.load(path/'paths.npz', allow_pickle=False) as data:
        actor = torch.jit.load(str(path/'actor.pt'), map_location='cpu').eval()
        result = verify_paths(data, row['cost'], actor)
    require(abs(result['gap']-row['optimality_gap']) < 1e-12, 'Reported gap differs')
    training = read(path/'training.json')
    require(len(training)*64 == row['transitions'], 'Training count differs')
    for i, record in enumerate(training):
        require(record['sampled_transitions'] == (i+1)*64, 'Sample counter differs')
        for key, update in record['updates'].items():
            require(update['min'] == update['max'] == row['optimizer_before'][key]['max']+i+1,
                    'Optimizer update sequence differs')
    require(all(row['parameter_changes'].values()), 'An actor/critic/target did not change')
    require(all(v['min'] > row['optimizer_before'][k]['max'] for k,v in row['optimizer_after'].items()),
            'Missing optimizer updates')
    checkpoint = path/'checkpoint'
    # Trusted owned checkpoints only. Independently inspect stored Adam counts.
    with (checkpoint/'learner_group/learner/state.pkl').open('rb') as f:
        learner = pickle.load(f)
    optimizers = learner['optimizer']
    for name, saved in optimizers.items():
        key = name.split('_')[-1]
        matches = [k for k in row['optimizer_after'] if name.endswith('_'+k)]
        key = max(matches, key=len) if matches else name
        expected = row['optimizer_after'][key]['min']
        require(all(int(v['step']) == expected for v in saved['state']['state'].values()), 'Checkpoint Adam steps differ')
    with (checkpoint/'lqr-supplement.pkl').open('rb') as f:
        extra = pickle.load(f)
    require(extra['replay']['_num_timesteps_added'] == row['replay_total_added'], 'Checkpoint replay count differs')
    require(sha(checkpoint/'lqr-supplement.pkl') == read(checkpoint/'lqr-integrity.json')['supplement']['sha256'],
            'Checkpoint supplement bytes differ')
    return {**result, 'seed': row['seed'], 'config': row['config'], 'transitions': row['transitions'],
            'optimizer_updates': row['optimizer_after']['policy']['min']}


def verify_selection(snapshot, fit_rows, freeze):
    evaluation = snapshot['evaluation']
    require(evaluation['phase'] == 'reported' and not evaluation['uncertain'], 'Incomplete Study')
    require(snapshot['n_suggested'] == snapshot['n_completed'] == 8, 'Wrong configuration count')
    expected = {(a, c, lr) for a in ((16,), (32,32)) for c in ((32,), (64,64)) for lr in (0,1)}
    actual = set()
    means = {}
    rows = []
    for tid, trial in snapshot['trials'].items():
        config = trial['config']['values']
        actual.add((tuple(config['actor_hiddens']), tuple(config['critic_hiddens']), config['lr_recipe']))
        reps = evaluation['tuning'][tid]
        require([r['seed'] for r in reps] == [1101,1102], 'Tuning seeds differ')
        costs = []
        for rep in reps:
            raw = fit_rows[rep['result']['trial_id']]
            require(raw['config'] == config and raw['seed'] == rep['seed'], 'Fit/config binding differs')
            require(raw['cost'] == rep['result']['objective_value'], 'Fit/Study score differs')
            costs.append(raw['cost'])
        means[tid] = math.fsum(costs)/2
        require(means[tid] == snapshot['results'][tid]['objective_value'], 'Tuning mean differs')
        rows.append({'trial_id':tid, 'config':config, 'costs':costs, 'mean_cost':means[tid]})
    require(actual == expected, 'Incomplete joint Cartesian roster')
    selected = min(means, key=means.get)
    require(evaluation['selection'] == freeze['selection'] == [selected], 'Wrong frozen selection')
    require(freeze['snapshot']['evaluation']['phase'] == 'selection_frozen' and
            not freeze['snapshot']['evaluation']['final'], 'Freeze was not prospective')
    final = evaluation['final'][selected]
    require([r['seed'] for r in final] == [2101,2102], 'Final seeds differ')
    final_costs = []
    for rep in final:
        raw = fit_rows[rep['result']['trial_id']]
        require(raw['started_epoch'] > freeze['epoch'], 'Final training preceded freeze')
        require(raw['config'] == snapshot['trials'][selected]['config']['values'], 'Final model differs')
        require(raw['seed'] == rep['seed'] and raw['cost'] == rep['result']['objective_value'], 'Final result differs')
        final_costs.append(raw['cost'])
    require(len(fit_rows) == 18 and sum(r['transitions'] for r in fit_rows.values()) == 73728, 'Joint work differs')
    attempts = snapshot['resources']['attempts']
    require(len(attempts) == 18 and all(a['state'] == 'committed' and a['work'] == 4096 and a['breach'] is None for a in attempts),
            'Resource ledger differs')
    return {'selected':selected, 'selected_config':snapshot['trials'][selected]['config']['values'],
            'tuning_mean':means[selected], 'final_costs':final_costs,
            'final_mean':math.fsum(final_costs)/2, 'all_candidates':rows}


def verify_hardware(record):
    rows = record['results']
    require(len(rows) == 2 and len({r['pid'] for r in rows}) == 2, 'Worker processes not distinct')
    require(len({r['visible_devices'] for r in rows}) == 2, 'Same physical GPU')
    require({r['visible_devices'] for r in rows} == set(record['assigned_gpu_uuids']), 'GPU assignment differs')
    require(all(r['device'] == ['cuda:0'] and r['transitions'] == 512 for r in rows), 'GPU learner/work differs')
    overlap = min(r['training_finished_epoch'] for r in rows)-max(r['training_started_epoch'] for r in rows)
    require(overlap > 0 and overlap == record['overlap_seconds'], 'GPU training did not overlap')
    require(not set(rows[0]['cpu_affinity']) & set(rows[1]['cpu_affinity']), 'CPU placements overlap')
    return {'training_overlap_seconds':overlap, 'physical_gpu_uuids':record['assigned_gpu_uuids']}


def negative_controls(joint, hardware):
    from copy import deepcopy
    fit_paths = sorted((joint/'fits').glob('*/fit-result.json'))
    fit_rows = {p.parent.name: read(p) for p in fit_paths}
    sample = fit_paths[0].parent
    with np.load(sample/'paths.npz', allow_pickle=False) as loaded:
        data = dict(loaded)
    snapshot = read(joint/'study/rl-lqr-joint_checkpoint.json')
    freeze = read(joint/'study/selection-freeze.json')
    hardware_record = read(hardware/'hardware-result.json')
    controls = []
    def reject(name, fn):
        try:
            fn()
        except ValueError:
            controls.append(name)
        else:
            raise AssertionError('False evidence accepted: '+name)
    reject('fabricated_cost', lambda: verify_paths(data, read(sample/'fit-result.json')['cost']+.1))
    bad = deepcopy(data); bad['noise'][0,0] = 0.
    reject('wrong_noise_law', lambda: verify_paths(bad, read(sample/'fit-result.json')['cost']))
    bad_action = deepcopy(data); bad_action['actions'][0,0] = 2.
    reject('infeasible_action', lambda: verify_paths(bad_action, read(sample/'fit-result.json')['cost']))
    wrong = deepcopy(snapshot); wrong['evaluation']['selection'] = ['nonexistent']
    reject('wrong_selection', lambda: verify_selection(wrong, fit_rows, freeze))
    late = deepcopy(freeze); late['epoch'] = 1e12
    reject('retrospective_freeze', lambda: verify_selection(snapshot, fit_rows, late))
    bad_hardware = deepcopy(hardware_record)
    bad_hardware['results'][1]['visible_devices'] = bad_hardware['results'][0]['visible_devices']
    reject('same_gpu', lambda: verify_hardware(bad_hardware))
    serial = deepcopy(hardware_record)
    serial['results'][1]['training_started_epoch'] = serial['results'][0]['training_finished_epoch']+1
    reject('serial_gpu_work', lambda: verify_hardware(serial))
    return controls
