"""Independent finite mathematics. No production model/optimizer imports.

Forward dense layers, Bellman derivatives, manual backpropagation, direct GP
conditioning and categorical probability identities reconstruct retained work.
Same-runtime production replay is a separate, explicitly weaker identity check.
"""
from copy import deepcopy
import hashlib
import json
import math

import numpy as np

ATOL, RTOL = 2e-10, 2e-9


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def close(actual, expected, name):
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all() or not np.allclose(a, b, atol=ATOL, rtol=RTOL):
        raise ValueError('Independent population reference differs: '+name)


def equal(actual, expected, name):
    if actual != expected:
        raise ValueError('Population identity differs: '+name)


def probabilities(outputs, actions):
    z = np.asarray(outputs, dtype=float)[:, :actions]
    shifted = z-z.max(axis=1, keepdims=True)
    logp = shifted-np.log(np.exp(shifted).sum(axis=1, keepdims=True))
    return np.exp(logp), logp


def objective(task, outputs, teacher_outputs, weight):
    """Independent finite-horizon Bellman and softmax derivatives."""
    rewards, transitions = np.asarray(task['rewards']), np.asarray(task['transitions'])
    initial = np.asarray(task['initial'])
    outputs, teacher_outputs = np.asarray(outputs), np.asarray(teacher_outputs)
    states, actions = rewards.shape
    p, logp = probabilities(outputs, actions)
    teacher, logteacher = probabilities(teacher_outputs, actions)
    kernel = np.sum(p[:, :, None]*transitions, axis=1)
    expected_reward = np.sum(p*rewards, axis=1)
    horizon, discount = task['horizon'], task['discount']
    values = [np.zeros(states) for _ in range(horizon+1)]
    for step in reversed(range(horizon)):
        values[step] = expected_reward+discount*kernel@values[step+1]
    distribution = initial.copy()
    occupancy, derivative = np.zeros(states), np.zeros((states, actions))
    for step in range(horizon):
        occupancy += distribution
        action_values = rewards+discount*np.sum(transitions*values[step+1], axis=2)
        derivative += discount**step*distribution[:, None]*action_values
        distribution = distribution@kernel
    normalized = occupancy/occupancy.sum()
    policy_kl = np.sum(normalized[:, None]*teacher*(logteacher-logp))
    residual = outputs[:, -1]-teacher_outputs[:, -1]
    value_error = np.sum(normalized*residual**2)/2
    expected_return = initial@values[0]
    c = task['coefficients']
    rl = 1-weight if c['rl'] is None else c['rl']
    loss = weight*(c['policy']*policy_kl+2*c['value_squared']*value_error)-rl*expected_return
    gradient = np.zeros_like(outputs, dtype=float)
    gradient[:, :actions] = weight*c['policy']*normalized[:, None]*(p-teacher)
    gradient[:, :actions] -= rl*p*(derivative-np.sum(p*derivative, axis=1, keepdims=True))
    gradient[:, -1] = weight*2*c['value_squared']*normalized*residual
    return {'loss': loss, 'policy_kl': policy_kl, 'value_error': value_error,
            'return': expected_return, 'occupancy': occupancy}, gradient


def forward(member, observations):
    config, tensors = member['architecture'], member['tensors']
    if config['activation'] != 'tanh' or config['normalization'] != 'none':
        raise ValueError('Independent population math covers only declared tanh/no-normalization models')
    values = [np.asarray(observations, dtype=float)]
    for layer in range(config['depth']+1):
        prefix = str(2*layer)
        value = values[-1]@np.asarray(tensors[prefix+'.weight']).T+np.asarray(tensors[prefix+'.bias'])
        values.append(np.tanh(value) if layer < config['depth'] else value)
    return values


def gradients(member, observations, output_gradient):
    activations = forward(member, observations)
    result, delta = {}, output_gradient.copy()
    for layer in reversed(range(member['architecture']['depth']+1)):
        prefix = str(2*layer)
        result[prefix+'.weight'] = delta.T@activations[layer]
        result[prefix+'.bias'] = delta.sum(axis=0)
        delta = delta@np.asarray(member['tensors'][prefix+'.weight'])
        if layer:
            delta *= 1-activations[layer]**2
    return result


def score(task, member):
    outputs = forward(member, task['observations'])[-1]
    return float(objective(task, outputs, outputs, 0)[0]['return'])


def verify_store(task, envelope, initials, name, checkpoint_scores):
    state = envelope['payload']
    equal(envelope['sha256'], digest(state), name+' checksum')
    equal(state['objective'], digest(task), name+' objective')
    equal(set(initials), set(state['events']), name+' initial tensor coverage')
    members = deepcopy(state['initial_members'])
    lower = upper = 0
    lineage = []
    for ident, event in state['events'].items():
        request, candidate = event['request'], deepcopy(initials[ident])
        parent, child = request['parent'], request['child']
        equal(event['teacher'], members[parent], name+' teacher')
        equal(event['teacher_sha256'], digest(members[parent]), name+' teacher identity')
        equal(event['child_before_sha256'], digest(members[child]), name+' child identity')
        equal(candidate['architecture'], request['architecture'], name+' architecture')
        equal(candidate['optimizer'], request['optimizer'], name+' optimizer')
        if request['mode'] in {'TRAIN', 'COPY'}:
            equal(candidate['tensors'], members[parent]['tensors'], name+' copied tensors')
            equal(candidate['updates'], members[parent]['updates'], name+' copied update count')
            if request['optimizer_policy'] == 'COPY':
                equal(candidate['velocity'], members[parent]['velocity'], name+' copied momentum')
        else:
            equal(candidate['updates'], 0, name+' reset updates')
        if request['optimizer_policy'] == 'RESET':
            for value in candidate['velocity'].values():
                close(value, np.zeros_like(value), name+' reset momentum')
        count = event['completed_updates']
        if type(count) is not int or not 0 <= count <= len(request['weights']) or type(event['inflight']) is not bool:
            raise ValueError('Invalid retained update count')
        equal(len(event['trace']), count, name+' trace length')
        teacher_outputs = forward(event['teacher'], task['observations'])[-1]
        checkpoint_scores[name, ident, 0] = score(task, candidate)
        for index in range(count):
            outputs = forward(candidate, task['observations'])[-1]
            components, derivative = objective(task, outputs, teacher_outputs, request['weights'][index])
            for key, actual in event['trace'][index].items():
                close(actual, components[key], name+' trace '+key)
            equal(set(event['trace'][index]), {'loss', 'policy_kl', 'value_error', 'return'}, name+' trace fields')
            gradient = gradients(candidate, task['observations'], derivative)
            for key in candidate['tensors']:
                velocity = request['optimizer']['momentum']*np.asarray(candidate['velocity'][key])+gradient[key]
                tensor = np.asarray(candidate['tensors'][key])-request['optimizer']['learning_rate']*velocity
                candidate['velocity'][key], candidate['tensors'][key] = velocity.tolist(), tensor.tolist()
            candidate['updates'] += 1
            checkpoint_scores[name, ident, index+1] = score(task, candidate)
        for field in ['tensors', 'velocity']:
            equal(set(candidate[field]), set(event['candidate'][field]), name+' tensor names')
            for key, expected in candidate[field].items():
                close(event['candidate'][field][key], expected, name+' '+field+' '+key)
        for field in ['architecture', 'optimizer', 'updates']:
            equal(event['candidate'][field], candidate[field], name+' '+field)
        lower += count
        upper += count+int(event['inflight'])
        if event['status'] == 'committed':
            equal(count, len(request['weights']), name+' committed work')
            equal(event['inflight'], False, name+' committed uncertainty')
            equal(event['result_sha256'], digest(event['candidate']), name+' result identity')
            members[child] = deepcopy(event['candidate'])
            lineage.append({'event': ident, 'parent': parent, 'child': child,
                            'teacher_sha256': event['teacher_sha256'], 'result_sha256': event['result_sha256']})
        elif event['status'] not in {'pending', 'failed', 'interrupted'}:
            raise ValueError('Unknown transfer state')
    equal(state['members'], members, name+' final members')
    equal(state['lineage'], lineage, name+' lineage')
    if upper > state['max_updates']:
        raise ValueError('Physical work exceeds update budget')
    return lower, upper


def kernel(left, right, options, numeric=(0,), categorical=(1,)):
    """Scalar loops deliberately separate from the vectorized production kernel."""
    result = np.zeros((len(left), len(right)))
    o = options
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            temporal = (1-o['decay'])**(abs(a[0]-b[0])/2)
            distance2 = sum(((a[k+1]-b[k+1])/o['length'])**2 for k in numeric)
            n = math.exp(-distance2/2) if o['family'] == 'pb2_mix' else (1+math.sqrt(5*distance2)+5*distance2/3)*math.exp(-math.sqrt(5*distance2))
            overlap = sum(a[k+1] == b[k+1] for k in categorical)/len(categorical)
            c = overlap if o['family'] == 'pb2_mix' else math.exp(overlap/o['categorical_length'])
            if o['family'] == 'pb2_mix':
                value = (1-o['mixture'])*(n+c)*temporal+o['mixture']*n*c*temporal**2
            else:
                value = (n+c+n*c)*temporal/2
            result[i, j] = o['amplitude']*value
    return result


def posterior(x, y, query, options, pending=(), numeric=(0,), categorical=(1,)):
    observed = kernel(x, x, options, numeric, categorical)+options['noise']*np.eye(len(x))
    mean = kernel(query, x, options, numeric, categorical)@np.linalg.solve(observed, y)
    augmented = [*x, *pending]
    covariance = kernel(augmented, augmented, options, numeric, categorical)+options['noise']*np.eye(len(augmented))
    cross = kernel(query, augmented, options, numeric, categorical)
    variance = np.diag(kernel(query, query, options, numeric, categorical)-cross@np.linalg.solve(covariance, cross.T))
    return mean, np.maximum(variance, 0)


def verify_bandit(raw):
    for row in raw['distributions']:
        weights = np.asarray(row['weights'])/max(row['weights'])
        clipped = np.asarray(row['clipped_weights'])
        gamma, batch, count = row['gamma'], row['batch'], len(weights)
        threshold = clipped.max()
        close(clipped, np.minimum(weights, threshold), 'bandit clipping')
        p = batch*((1-gamma)*clipped/clipped.sum()+gamma/count)
        close(row['probabilities'], p, 'bandit marginals')
        close(p.sum(), batch, 'bandit batch size')
        if np.any(p > 1+ATOL) or np.any(p < 0):
            raise ValueError('Invalid bandit marginals')
        expected = list(range(count)) if batch == count else np.flatnonzero(weights >= threshold).tolist() if np.any(weights != clipped) else []
        equal(row['clipped'], expected, 'bandit capped identities')
        if expected and batch < count:
            close(p[expected], np.ones(len(expected)), 'capped inclusion must equal one')
    envelope = raw['bandit']
    state = envelope['payload']
    equal(envelope['sha256'], digest(state), 'bandit checksum')
    o = state['options']
    weights = np.ones(o['categories'])/o['categories']
    for index, row in enumerate(state['history']):
        selection = row['selection']
        equal(selection['round'], index, 'bandit round')
        clipped = np.asarray(selection['clipped_weights'])
        normalized = weights/weights.max()
        close(clipped, np.minimum(normalized, clipped.max()), 'bandit temporal clipping')
        p = o['batch']*((1-o['gamma'])*clipped/clipped.sum()+o['gamma']/len(weights))
        close(selection['probabilities'], p, 'bandit temporal marginals')
        selected = selection['selected']
        if len(selected) != o['batch'] or len(set(selected)) != len(selected):
            raise ValueError('Bandit selection cardinality differs')
        equal(set(row['rewards']), {str(i) for i in selected}, 'bandit feedback')
        following = clipped.copy()
        for arm in selected:
            reward = row['rewards'][str(arm)]
            if not 0 <= reward <= 1:
                raise ValueError('Unbounded bandit feedback')
            if arm not in selection['clipped']:
                following[arm] *= math.exp(o['batch']*o['gamma']*reward/(len(weights)*p[arm]))
        following += math.e*o['sharing']*clipped.sum()/len(weights)
        weights = following/following.sum()
    close(state['weights'], weights, 'bandit weight update including all-arm sharing')


def verify_controller(task, state, store):
    events = store['events']
    region = None
    for index, row in enumerate(state['rounds']):
        equal(row['status'], 'complete', 'round status')
        equal(row['index'], index, 'round index')
        for name, old in row['training_inputs'].items():
            event = events[f'pbt:{index}:train:{name}']
            close(old['score'], score(task, event['teacher']), 'training input score')
            equal(old['optimizer'], event['teacher']['optimizer'], 'training input optimizer')
            equal(old['architecture'], event['teacher']['architecture'], 'training input architecture')
            close(row['scores'][name], score(task, event['candidate']), 'selection score')
        ranking = sorted(row['scores'], key=lambda name: (-row['scores'][name], name))
        count = max(1, math.floor(len(ranking)*state['options']['quantile']))
        equal([a['child'] for a in row['plan']], ranking[-count:], 'truncation losers')
        for action in row['plan']:
            if action['parent'] not in ranking[:count]:
                raise ValueError('Exploit teacher is not an eligible winner')
            request = events[action['event_id']]['request']
            for key, value in action.items():
                if key not in {'factor', 'event_id'}:
                    equal(request[key], value, 'exploit plan '+key)
            if 'factor' in action:
                lo, hi = state['options']['learning_rate_bounds']
                teacher = events[action['event_id']]['teacher']
                close(request['optimizer']['learning_rate'], min(hi, max(lo, teacher['optimizer']['learning_rate']*action['factor'])), 'PBT multiplicative exploration')
        if 'exploration' not in row:
            continue
        diagnostic = row['exploration']
        options, pending = diagnostic['gp_options'], []
        x, y = diagnostic['x'], diagnostic['increments']
        cursor = 0
        c = state['options']['explorer']
        bg = options['family'] == 'bgpbt'
        for time, old_round in enumerate(state['rounds'][:index+1]):
            for name, old in old_round['training_inputs'].items():
                close(y[cursor], (old_round['scores'][name]-old['score'])/c['increment_bound'], 'observed increment')
                lo, hi = c['learning_rate_bounds']
                coordinate = math.log(old['optimizer']['learning_rate']/lo)/math.log(hi/lo)
                category = c['momenta'].index(old['optimizer']['momentum'])
                architecture = old['architecture']
                point = [time, coordinate, category]
                if bg:
                    point = [time, coordinate, architecture['width']/512, architecture['depth']/4, category,
                             ['relu', 'tanh', 'elu', 'gelu', 'swish'].index(architecture['activation']),
                             ['none', 'layer_norm', 'spectral_norm'].index(architecture['normalization'])]
                close(x[cursor], point, 'GP input context')
                cursor += 1
        equal(len(y), cursor, 'GP observation coverage')
        numeric, categorical = ((0, 1, 2), (3, 4, 5)) if bg else ((0,), (1,))
        if bg:
            best = max(row['scores'].values())
            if region is None:
                region = {'numeric': c['initial_numeric'], 'categorical': c['initial_categorical'],
                          'successes': 0, 'failures': 0, 'best': best, 'restarts': 0, 'start_round': 0}
            elif best > region['best']:
                region.update(best=best, successes=region['successes']+1, failures=0)
            else:
                region.update(failures=region['failures']+1, successes=0)
            if region['successes'] >= c['success_tolerance']:
                region.update(numeric=min(1, region['numeric']*c['multiplier']),
                              categorical=min(1, region['categorical']*c['multiplier']), successes=0)
            if region['failures'] >= c['failure_tolerance']:
                region.update(numeric=region['numeric']/c['multiplier'],
                              categorical=region['categorical']/c['multiplier'], failures=0)
            collapsed = region['numeric'] < c['minimum_numeric'] or region['categorical'] < c['minimum_categorical']
            equal(diagnostic['restart'] is not None, collapsed, 'trust region collapse')
            if collapsed:
                region.update(numeric=c['initial_numeric'], categorical=c['initial_categorical'],
                              successes=0, failures=0, restarts=region['restarts']+1, start_round=index)
            equal(diagnostic['region'], region, 'trust region transition')
            restart = diagnostic['restart']
            if restart:
                candidates = [[index+1, *point[1:]] for point in x]
                mean, variance = posterior(x, y, candidates, restart['gp_options'], (), numeric, categorical)
                expected = mean+np.sqrt(state['options']['explorer']['beta']*variance)
                close(restart['ucb'], expected, 'global restart acquisition')
                equal(restart['index'], int(np.argmax(expected)), 'global restart selection')
                equal(restart['center'], candidates[restart['index']], 'global restart center')
            indices = diagnostic['local_indices']
            equal(indices, [i for i, point in enumerate(x) if point[0] >= region['start_round']], 'local GP reset')
            x, y = [x[i] for i in indices], [y[i] for i in indices]
        else:
            verify_bandit({'distributions': [], 'bandit': diagnostic['bandit']})
            equal(diagnostic['selection'], diagnostic['bandit']['payload']['pending'], 'categorical pending selection')
        equal(len(diagnostic['acquisitions']), len(row['plan']), 'acquisition coverage')
        for action, acquisition in zip(row['plan'], diagnostic['acquisitions']):
            evaluations = acquisition['evaluations']
            query = [v['point'] if bg else [index+1, v['coordinate'], acquisition['category']] for v in evaluations]
            mean, variance = posterior(x, y, query, options, pending, numeric, categorical)
            expected = mean+np.sqrt(state['options']['explorer']['beta']*variance)
            close([v['ucb'] for v in evaluations], expected, 'acquisition evaluated UCB')
            selected = acquisition['selected']
            if bg:
                candidates = [v['ucb'] for v in evaluations if v['point'] == selected]
                if not candidates:
                    raise ValueError('Selected BG proposal was not evaluated')
                close(max(candidates), max(expected), 'BG evaluated maximizer')
                low, high = acquisition['numeric_bounds']
                if not low <= selected[1] <= high or selected[4] not in acquisition['categories']:
                    raise ValueError('Proposal outside mixed trust region')
                equal(selected[2:4], acquisition['center'][2:4], 'fixed numeric architecture context')
                equal(selected[5:], acquisition['center'][5:], 'fixed categorical architecture context')
                point = selected
            else:
                close(selected['ucb'], max(expected), 'PB2 evaluated maximizer')
                point = [index+1, selected['coordinate'], acquisition['category']]
            lo, hi = c['learning_rate_bounds']
            close(action['optimizer']['learning_rate'], lo*(hi/lo)**point[1], 'selected learning rate')
            equal(action['optimizer']['momentum'], c['momenta'][int(point[4] if bg else point[2])], 'selected momentum')
            pending.append(point)


def verify_slot(spec, raw):
    kind = spec['kind']
    if kind == 'algebra':
        equal([r['weight'] for r in raw['rows']], [0.0, 0.5, 1.0], 'algebra roster')
        for row in raw['rows']:
            components, gradient = objective(raw['objective'], row['outputs'], row['teacher_outputs'], row['weight'])
            for key in components:
                close(row['components'][key], components[key], 'MDP '+key)
            close(row['gradient'], gradient, 'MDP gradient')
        # Uniform policies have J=1/2 + (1/2)(1/2)(1/2)=5/8 here.
        close(raw['rows'][0]['components']['return'], 5/8, 'rational two-step return')
        return {'status': 'PASS', 'updates_lower': 0, 'updates_upper': 0}
    if kind == 'gp':
        equal([r['options']['family'] for r in raw['rows']], ['pb2_mix', 'bgpbt'], 'kernel roster')
        for row in raw['rows']:
            close(row['kernel'], kernel(row['x'], row['query'], row['options']), 'published kernel')
            for prefix, pending in [('', []), ('pending_', row['pending'])]:
                mean, variance = posterior(row['x'], row['y'], row['query'], row['options'], pending)
                close(row[prefix+'mean'], mean, 'posterior mean')
                close(row[prefix+'variance'], variance, 'posterior variance')
        return {'status': 'PASS', 'updates_lower': 0, 'updates_upper': 0}
    if kind == 'bandit':
        verify_bandit(raw)
        return {'status': 'PASS', 'updates_lower': 0, 'updates_upper': 0}
    task = raw['objective']
    stores = {name: value for name, value in raw['files'].items()
              if value.get('payload', {}).get('schema') == 'local_population_checkpoint_v1'}
    equal(set(stores), set(raw['initial_candidates']), 'population store coverage')
    if not stores:
        raise ValueError('Empty population evidence')
    lower = upper = 0
    checkpoint_scores = {}
    for name, store in stores.items():
        lo, hi = verify_store(task, store, raw['initial_candidates'][name], name, checkpoint_scores)
        lower += lo; upper += hi
    for name, value in raw['files'].items():
        payload = value['payload']
        equal(value['sha256'], digest(payload), name+' envelope')
        if payload.get('options', {}).get('method') == 'local_pbt_truncation_v1':
            directory = name.rsplit('/', 1)[0]+'/' if '/' in name else ''
            verify_controller(task, payload, stores[directory+'population.json']['payload'])
    if kind == 'interruption':
        equal(raw['outcome']['status'], 'interrupted', 'unknown update disposition')
        equal((lower, upper), (0, 1), 'unknown work interval')
        state = stores['population.json']['payload']
        equal(state['members'], state['initial_members'], 'interrupted child rollback')
    elif kind == 'transfer':
        equal(raw['outcome']['status'], 'committed', 'transfer outcome')
        equal((lower, upper), (3, 3), 'transfer work')
    elif kind == 'population':
        equal(len(raw['outcome']['rounds']), spec['rounds'], 'round coverage')
        equal((lower, upper), (2*spec['rounds'], 2*spec['rounds']), 'population work')
        if spec['method'] == 'bgpbt':
            equal(raw['outcome']['rounds'][1]['exploration']['region']['restarts'], 1, 'forced global restart')
    elif kind == 'generations':
        outcome = raw['outcome']
        equal(outcome['status'], 'complete', 'generation outcome')
        equal(outcome['accounting'], {'lower': lower, 'upper': upper, 'allocated': 10}, 'generation accounting')
        equal((lower, upper), (10, 10), 'exact generation work')
        program = raw['files']['program.json']['payload']
        equal(outcome, program, 'outer generation program')
        equal(len(program['generations']), 2, 'generation coverage')
        for index, generation in enumerate(program['generations']):
            control = raw['files'][f'generation-{index}/pbt.json']['payload']
            observations = [{'architecture': row['training_inputs'][name]['architecture'], 'score': value}
                            for row in control['rounds'] for name, value in row['scores'].items()]
            equal(generation['architecture_observations'], observations, 'architecture observations')
            equal(generation['trigger'], 'maximum_age', 'generation trigger')
            equal(generation['rounds'], 1, 'generation age')
        first = program['generations'][0]
        diagnostic = first['architecture_search']
        architecture_pool = program['contract']['architecture_pool']
        def point(architecture):
            return [0, architecture['width']/512, architecture['depth']/4,
                    ['relu', 'tanh', 'elu', 'gelu', 'swish'].index(architecture['activation']),
                    ['none', 'layer_norm', 'spectral_norm'].index(architecture['normalization'])]
        observations = diagnostic['observations']
        x = [point(row['architecture']) for row in observations]
        y = [row['score']/program['contract']['explorer']['increment_bound'] for row in observations]
        candidates = [point(config) for config in architecture_pool]
        mean, variance = posterior(x, y, candidates, diagnostic['gp_options'], (), (0, 1), (2, 3))
        equal(diagnostic['bo_indices'], [int(np.argmax(mean+np.sqrt(variance)))], 'architecture BO choice')
        chosen = diagnostic['bo_indices']+diagnostic['random_indices']
        equal(len(set(chosen)), 4, 'distinct oversampled architecture proposals')
        equal(first['proposals'], [architecture_pool[i] for i in chosen], 'architecture proposal identities')
        transfer = raw['files']['transfer-0/generation.json']['payload']
        alive = list(range(4))
        for row in transfer['rungs']:
            equal(set(row['scores']), {str(i) for i in alive}, 'halving score coverage')
            for i in alive:
                close(row['scores'][str(i)], checkpoint_scores[f'transfer-0/candidate-{i}.json', 'distill', row['target']], 'actual halving score')
            winners = sorted(alive, key=lambda i: (-row['scores'][str(i)], i))[:2]
            equal(row['survivors'], winners, 'halving selection')
            equal(row['eliminated'], [i for i in alive if i not in winners], 'halving eliminations')
            alive = winners
        equal(transfer['teacher_sha256'], digest(transfer['contract']['teacher']), 'frozen generation teacher')
        successors = {str(i): stores[f'transfer-0/candidate-{i}.json']['payload']['members']['student'] for i in alive}
        equal(transfer['survivors'], successors, 'halving successor tensors')
        generation_initial = {str(i): member for i, member in enumerate(successors.values())}
        equal(stores['generation-1/population.json']['payload']['initial_members'], generation_initial, 'published successor population')
        equal(outcome['final_members'], stores['generation-1/population.json']['payload']['members'], 'final population identity')
        equal(len(outcome['final_members']), 2, 'successor population size')
    return {'status': 'PASS', 'updates_lower': lower, 'updates_upper': upper}
