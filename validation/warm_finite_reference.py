"""Independent scalar-power, pairwise-rank and raw-store reconstruction.

No production warm selector or training objective is imported here.
"""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

from validation.warm_finite_contract import contract


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def bound(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _close(a, b):
    if type(a) not in (int, float) or not math.isfinite(a) or not math.isclose(a, b, rel_tol=2e-10, abs_tol=2e-12):
        raise ValueError('Warm mathematical reference differs')


def _space(transform='none'):
    return {'knobs': [{'name': 'eta', 'kind': 'continuous', 'bounds': [.125, .875],
        'transform': transform, 'condition': None, 'prior': None, 'note': ''}]}


def _signature(transform='none'):
    return bound([{key: value for key, value in _space(transform)['knobs'][0].items()
                   if key in {'name', 'kind', 'bounds', 'transform', 'condition'}}])


def uniforms(seed, count, transform='none'):
    values = np.random.RandomState(seed).uniform(size=count)
    if transform == 'log':
        return np.exp(math.log(.125)+values*(math.log(.875)-math.log(.125))).tolist()
    return (.125+.75*values).tolist()


def verify_raw(slot, raw, directory=None):
    spec = contract()
    names = [*spec['history_names'], 'target', 'cold']
    if raw['slot'] != slot or [r['study_id'] for r in raw['studies']] != names:
        raise ValueError('Warm fixed study roster differs')
    if len(raw['histories']) != 6 or [r['study_id'] for r in raw['histories']] != names[:6]:
        raise ValueError('Warm history roster differs')
    target = raw['context']
    cutoff = target['history_cutoff']
    if type(cutoff) not in (float, int) or not math.isfinite(cutoff):
        raise ValueError('Warm cutoff missing')
    expected_context = {'study_id': 'target', 'task_id': 'evaluation',
        'model_family': 'scalar-quadratic', 'task_domain': 'gradient-tuning',
        'objective_key': 'endpoint-squared-error',
        'direction': 'maximize' if slot['maximize'] else 'minimize',
        'history_cutoff': cutoff, 'endpoint_fidelity': 1.,
        'space_signature': _signature(), 'excluded_task_ids': ['evaluation']}
    if target != expected_context:
        raise ValueError('Warm target context differs')
    ranked, excluded = [], []
    for index, history in enumerate(raw['histories']):
        name = names[index]
        expected = {'study_id': name, 'task_id': 'evaluation' if name == 'held-out' else 'history-'+name,
            'model_family': 'scalar-quadratic' if slot['eligible'] else 'other-family',
            'task_domain': 'gradient-tuning', 'objective_key': 'endpoint-squared-error',
            'direction': expected_context['direction'], 'endpoint_fidelity': 1.,
            'space_signature': _signature('log' if name == 'wrong-space' else 'none'),
            'status': 'completed', 'schema': 'warm_history_snapshot_v1'}
        if any(history.get(k) != v for k,v in expected.items()):
            raise ValueError('Warm history identity differs')
        body = {k:v for k,v in history.items() if k != 'binding'}
        if history.get('binding') != bound(body):
            raise ValueError('Warm history binding differs')
        completed = history['completed_at']
        if (not isinstance(completed, (int, float)) or not math.isfinite(completed)
                or (completed > cutoff) != (name == 'future')):
            raise ValueError('Warm observed chronology differs')
        trials = history['trials']
        if len(trials) != 4 or [r['trial_id'] for r in trials] != [name+'_trial_'+str(i) for i in range(4)]:
            raise ValueError('Warm historical trial roster differs')
        reason = ('held_out' if name == 'held-out' else 'outside_history_cutoff' if name == 'future'
                  else 'incompatible_model_family' if not slot['eligible']
                  else 'incompatible_space_signature' if name == 'wrong-space' else None)
        if reason:
            excluded.append({'study_id': name, 'reason': reason})
        else:
            values = [(-1 if slot['maximize'] else 1)*r['value'] for r in trials]
            for trial, value in zip(trials, values):
                q = Fraction(2*sum(v < value for v in values)+sum(v == value for v in values), 2*len(values))
                ranked.append((q, name, trial['trial_id'], trial['config']))
    seeds, seen = [], set()
    for q, name, tid, config in sorted(ranked, key=lambda r:r[:3]):
        key = canonical(config)
        if key not in seen and len(seeds) < 3:
            seeds.append({'study_id': name, 'trial_id': tid, 'config': config,
                          'quantile': [q.numerator, q.denominator]})
            seen.add(key)
    body = {'schema': 'ranked_history_v1', 'context': expected_context, 'limit': 3,
        'seeds': seeds, 'excluded': sorted(excluded, key=lambda r:r['study_id']),
        'history_bindings': sorted([{'study_id': h['study_id'], 'sha256': h['binding']}
                                   for h in raw['histories']], key=lambda r:r['study_id'])}
    selection = {**body, 'binding': bound(body)}
    if raw['selection'] != selection:
        raise ValueError('Warm independent rank selection differs')
    initial = raw['initial_warm']
    if initial['selection'] != selection or initial['history'] or initial['base']['history'] or initial['trials']:
        raise ValueError('Warm initial target was contaminated by historical measurements')
    physical, reports = [], {}
    for index, row in enumerate(raw['studies']):
        name = names[index]
        count = 4 if index < 6 else 6
        h = slot['history_curvature'] if index < 6 else slot['target_curvature']
        scale = slot['scale']*(3. if name == 'B' else 1.) if index < 6 else 1.
        offset = 100. if name == 'B' else 0.
        seed = spec['history_seeds'][index] if index < 6 else 13
        transform = 'log' if name == 'wrong-space' else 'none'
        if (row['curvature'], row['scale'], row['offset'], row['seed'], row['space']) != (h,scale,offset,seed,_space(transform)):
            raise ValueError('Warm training model/options differ')
        rates = uniforms(seed, count, transform)
        if name == 'target':
            rates = [r['config']['eta'] for r in seeds]+rates[:count-len(seeds)]
        snapshot, result = row['snapshot'], row['result']
        trial_names = [name+'_trial_'+str(i) for i in range(count)]
        if (set(snapshot['trials']) != set(trial_names) or set(snapshot['results']) != set(trial_names)
                or snapshot['pending'] or not snapshot['finished'] or snapshot['n_completed'] != count
                or snapshot['budget'] != count or snapshot['space'] != _space(transform)
                or snapshot['maximize'] != slot['maximize'] or result['n_trials'] != count
                or result['total_cost'] != count*4 or result['status'] != 'completed'
                or result['history'] != [snapshot['results'][tid] for tid in trial_names]):
            raise ValueError('Warm completed Study/result ledger differs')
        if len(row['updates']) != count*4:
            raise ValueError('Warm actual work count differs')
        losses = []
        for i, (tid, eta) in enumerate(zip(trial_names, rates)):
            trial, output = snapshot['trials'][tid], snapshot['results'][tid]
            if trial['trial_id'] != tid or set(trial['config']['values']) != {'eta'}:
                raise ValueError('Warm trial identity differs')
            _close(trial['config']['values']['eta'], eta)
            for step, update in enumerate(row['updates'][4*i:4*i+4],1):
                if update['trial_id'] != tid or update['step'] != step:
                    raise ValueError('Warm repeated or missing update')
                _close(update['eta'], eta)
                _close(update['state'], (1-eta*h)**step)
                physical.append({'sequence':len(physical),'study':name,**update})
            value = (-1 if slot['maximize'] else 1)*(offset+scale*(1-eta*h)**8)
            for field in [trial['value'],output['objective_value']]:
                _close(field,value)
            if (trial['status'] != 'completed' or trial['cost'] != 4 or trial['seed'] != seed+i
                    or output['trial_id'] != tid or output['cost'] != 4 or output['fidelity'] != 1.
                    or output['status'] != 'completed'):
                raise ValueError('Warm measured result/work differs')
            if index < 6:
                history_trial = raw['histories'][index]['trials'][i]
                expected_trial = {'trial_id':tid,'config':trial['config']['values'],
                    'seed':seed+i,'fidelity':1.,'value':output['objective_value'],'cost':4.,
                    'parent_trial_id':None,'status':'completed'}
                if history_trial != expected_trial:
                    raise ValueError('Warm frozen history does not match actual training')
            losses.append(value)
        best = (max if slot['maximize'] else min)(range(count),key=lambda i:losses[i])
        _close(result['best_value'],losses[best])
        if result['best_config'] != snapshot['trials'][trial_names[best]]['config']:
            raise ValueError('Warm incumbent differs')
        state = snapshot['searcher_state']
        if name == 'target':
            if (state['selection'] != selection or state['history'] != result['history']
                    or state['base']['history'] != result['history']
                    or state['queue']['cursor'] != len(seeds)):
                raise ValueError('Warm target/base observations or seed cursor differ')
            recovery = row['recovery']
            before, after = recovery['before'], recovery['after']
            if (before != after or before['pending'] != ['target_trial_2']
                    or set(before['results']) != {'target_trial_0','target_trial_1'}
                    or before['searcher_state']['selection'] != selection
                    or before['trials']['target_trial_2']['config'] != snapshot['trials']['target_trial_2']['config']):
                raise ValueError('Warm pending recovery differs')
            if any(snapshot['results'][tid] != outcome for tid,outcome in before['results'].items()):
                raise ValueError('Warm committed prefix changed')
        elif row['recovery'] is not None:
            raise ValueError('Unexpected warm recovery boundary')
        if index >= 6:
            eta_star = min(.875,max(.125,1/h))
            optimum = (1-eta_star*h)**8
            observed = (-1 if slot['maximize'] else 1)*result['best_value']
            if observed < optimum-2e-12:
                raise ValueError('Warm result below mathematical optimum')
            reports[name] = {'best_loss':observed,'optimal_eta':eta_star,'optimal_loss':optimum,'regret':observed-optimum}
    if raw['physical_updates'] != len(physical) or len(physical) != 144:
        raise ValueError('Warm total work differs')
    if directory is not None:
        directory = Path(directory)
        if [json.loads(line) for line in (directory/'physical-updates.jsonl').read_text().splitlines()] != physical:
            raise ValueError('Warm incremental physical record differs')
        for row in raw['studies']:
            if json.loads((directory/(row['study_id']+'-training.json')).read_text()) != row:
                raise ValueError('Warm retained training record differs')
        target_row = raw['studies'][6]
        for side in ['before','after']:
            if json.loads((directory/('recovery-'+side+'.json')).read_text()) != target_row['recovery'][side]:
                raise ValueError('Warm retained checkpoint differs')
        backup = directory/'store-backup/database.sqlite3'
        if hashlib.sha256(backup.read_bytes()).hexdigest() != raw['backup']['sha256']:
            raise ValueError('Warm retained database differs')
        if json.loads((directory/'store-backup/manifest.json').read_text()) != raw['backup']:
            raise ValueError('Warm database manifest differs')
        connection = sqlite3.connect(backup.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
        try:
            snapshots = {name:json.loads(value) for name,value in connection.execute('SELECT study_id,payload FROM study_snapshots')}
            histories = {name:json.loads(value) for name,value in connection.execute('SELECT study_id,payload FROM warm_history')}
            if snapshots != {r['study_id']:r['snapshot'] for r in raw['studies']} or histories != {r['study_id']:r for r in raw['histories']}:
                raise ValueError('Warm SQLite snapshots differ')
        finally:
            connection.close()
    return {'slot':slot['id'],'gradient_updates':len(physical),'selected_seeds':len(seeds),
            'excluded':excluded,'target':reports['target'],'cold':reports['cold'],
            'empirical_speedup_established':False,'default_activated':False}
