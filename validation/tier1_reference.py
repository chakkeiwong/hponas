"""Independent finite mathematical checks; no production numerical evaluators.

Production-method identity replay is deliberately separate in tier1_campaign.
Fixed floating-point tolerances below are engineering envelopes, not proofs of
roundoff bounds or optimizer performance.
"""
from fractions import Fraction as Q
from itertools import combinations
import hashlib
import json
import math

import numpy as np


def near(actual, expected, *, atol=1e-11, rtol=1e-9):
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all() or not np.allclose(a, b, atol=atol, rtol=rtol):
        raise ValueError('Independent Tier-1 numerical reconstruction differs')


def front(points):
    return [i for i, point in enumerate(points) if not any(
        all(a <= b for a, b in zip(other, point)) and other != point for other in points)]


def union(points):
    points = list(dict.fromkeys(tuple(p) for p in points))
    points = [points[i] for i in front(points)]
    volume = Q(0)
    for count in range(1, len(points)+1):
        for subset in combinations(points, count):
            volume += (-1)**(count+1)*(1-max(p[0] for p in subset))*(1-max(p[1] for p in subset))
    return volume


def vector(spec, raw):
    from validation.tuning_reference import spline
    observed, state = raw['observations'], raw['snapshot']
    known = {sum(1 << (int(Q(k)*8)-1) for k in r['knots']): r for r in spline()['architectures']}
    history = observed['history']
    if (len(history) != spec['trials'] or observed['method'] != spec['method']
            or list(state['results'].values()) != history or observed['n_trials'] != spec['trials']):
        raise ValueError('Vector corpus/history differs')
    points, ids = [], []
    for result in history:
        trial = state['trials'][result['trial_id']]
        exact = known[trial['config']['values']['architecture_id']]
        row = result['metadata']['multi_objective']
        if (row['identity'] != observed['metrics']['identity'] or row['identity'] != state['multi_objective']['identity']
                or row['objectives']['hidden_units'] != exact['width']
                or row['constraints'] != {'hidden_units': exact['width']}
                or row['feasible'] != (exact['width'] <= 5) or row['work'] != 1
                or result['fidelity'] != 1 or result['status'] != 'completed'):
            raise ValueError('Vector physical observation/metric identity differs')
        near(row['objectives']['integrated_error'], float(Q(exact['integrated_error'])), atol=1e-12)
        if row['feasible']:
            # Metric decisions use the actual floating observations. The separate
            # rational model check above constrains their physical correctness.
            points.append((Q(row['objectives']['integrated_error'])*128, Q(exact['width'], 7)))
            ids.append(result['trial_id'])
    expected_ids = [ids[i] for i in front(points)]
    if observed['metrics']['front_trial_ids'] != expected_ids:
        raise ValueError('Reported Pareto set differs')
    near(observed['metrics']['hypervolume'], float(union(points)), atol=1e-12)
    if observed['metrics']['total_work'] != len(history) or not observed['metrics']['exact_work']:
        raise ValueError('Vector fit accounting differs')
    return {'fits': len(history), 'hypervolume': observed['metrics']['hypervolume']}


def pibo(spec, raw):
    from validation.cost_acceptance import exact_loss, close
    if raw['spec'] != spec or len(raw['observations']) != 6:
        raise ValueError('piBO method/corpus differs')
    for row in raw['observations']:
        if set(row['config']) != {'eta'} or not .025 <= row['config']['eta'] <= .625 or row['cost'] != 8:
            raise ValueError('piBO physical configuration/work differs')
        eta = Q(row['config']['eta'])
        if len(row['updates']) != 8:
            raise ValueError('piBO physical work incomplete')
        for step, update in enumerate(row['updates'], 1):
            checkpoint = update['checkpoint']
            if (update['step'] != step or checkpoint['eta'] != float(eta)
                    or checkpoint['iterations'] != step or checkpoint['gradient_steps'] != step):
                raise ValueError('piBO training checkpoint differs')
            a, b = (1-eta)**step/10, (1-3*eta)**step
            close(update['value'], a*a+b*b)
            near(checkpoint['state'], [float((3*a-4*b)/5), float((4*a+3*b)/5)], atol=1e-12)
        close(row['value'], exact_loss(float(eta)))
    probes = raw['probes']
    if spec['advice'] == 'none':
        if probes:
            raise ValueError('No-prior method supplied prior scores')
    else:
        if [p['observations'] for p in probes] != [3, 4, 5]:
            raise ValueError('Actual piBO acquisition probes missing')
        center = spec['center']
        mass = .12*math.sqrt(math.pi)/1.2*(math.erf((.625-center)/.12)-math.erf((.025-center)/.12))
        for probe in probes:
            if probe['etas'] != [.025, .325, .625]:
                raise ValueError('piBO probe coordinates differ')
            scores = [.05+.95*math.exp(-((x-center)/.12)**2)/mass for x in probe['etas']]
            near(probe['guarded_scores'], scores)
            expected = [b+2/probe['observations']*math.log(s) for b, s in zip(probe['base'], scores)]
            near(probe['weighted'], expected)
            if min(scores) < .05:
                raise ValueError('Positive score guard failed')
    return {'physical_updates': 48, 'prior_probes': len(probes),
            'best_loss': min(row['value'] for row in raw['observations'])}


def advisory(spec, raw):
    events = raw['events']
    expected_reports = [('A',1),('B',1),('C',1),('D',1),('A',2),('B',2),('A',4),('B',4)]
    if [(e['trial'],e['fidelity']) for e in events if e['kind']=='report'] != expected_reports:
        raise ValueError('Advisory report inventory differs')
    promotions = [e for e in events if e['kind'] == 'promote']
    if promotions != [{'kind':'promote','fidelity':1,'promotions':[['A',2],['B',2]]},
                      {'kind':'promote','fidelity':2,'promotions':[['A',4],['B',4]]},
                      {'kind':'promote','fidelity':4,'promotions':[]}]:
        raise ValueError('Feasible reversal or absolute-veto promotion differs')
    for event in events:
        if event['kind'] == 'report':
            expected = 'stop' if event['trial'] in {'C','D'} or event['fidelity'] == 4 else 'pause'
            if event['decision'] != expected:
                raise ValueError('Advisory report decision differs')
    return {'feasible_full_fidelity': ['A','B'], 'vetoed': ['C','D'], 'rank_reversal_preserved': True}


def _rank(x):
    from scipy.special import ndtri
    flat = x.reshape(-1)
    order = sorted(set(flat))
    ranks, offset = {}, 0
    for value in order:
        count = int(np.sum(flat == value))
        ranks[value] = offset+(count+1)/2
        offset += count
    return ndtri((np.array([ranks[v] for v in flat]).reshape(x.shape)-3/8)/(flat.size+1/4))


def _statistics(x):
    m, n = x.shape
    means = np.array([sum(row)/n for row in x])
    within = sum(sum((row-mu)**2)/(n-1) for row,mu in zip(x,means))/m
    if within <= 0:
        return float('inf'), 0.
    between = sum((means-sum(means)/m)**2)/(m-1)
    variance = (n-1)/n*within+between
    # Direct lag products replace the production FFT autocovariance.
    rho = [1.]
    for lag in range(1,n):
        covariance = sum(sum((row[:n-lag]-mu)*(row[lag:]-mu))/n for row,mu in zip(x,means))/m
        rho.append(1-(within-covariance)/variance)
    pairs = []
    for lag in range(0,n-1,2):
        value = rho[lag]+rho[lag+1]
        if value < 0:
            break
        pairs.append(min(value,pairs[-1]) if pairs else value)
    tau = max(1.,-1+2*sum(pairs))
    return max(1.,math.sqrt(variance/within)), min(m*n,m*n/tau)


def diagnostics(chains):
    x = np.array(chains, dtype=float)
    if x.ndim != 3 or x.shape[2] != 1 or not np.isfinite(x).all():
        raise ValueError('Invalid Gaussian chain array')
    half = x.shape[1]//2
    split = np.concatenate((x[:,:half,0],x[:,-half:,0]))
    if any(np.var(row) == 0 for row in split):
        row = {'bulk_ess':0.,'tail_ess':0.,'rhat':float('inf')}
    else:
        rank, folded = _rank(split), _rank(abs(split-np.median(split)))
        lo,hi = np.quantile(split,[.05,.95])
        row = {'bulk_ess':_statistics(rank)[1],
               'tail_ess':min(_statistics((split<=lo).astype(float))[1],_statistics((split>=hi).astype(float))[1]),
               'rhat':max(_statistics(rank)[0],_statistics(folded)[0])}
    return {'marginals':[row], **row}


def check_diagnostics(actual, expected):
    if set(actual) != set(expected):
        raise ValueError('Diagnostic field inventory differs')
    for key in ['rhat','bulk_ess','tail_ess']:
        if math.isfinite(expected[key]):
            near(actual[key], expected[key])
        elif actual[key] != 'Infinity':
            raise ValueError('Nonfinite diagnostic was hidden')
    if len(actual['marginals']) != 1:
        raise ValueError('Gaussian marginal inventory differs')
    for key,value in actual['marginals'][0].items():
        if value != actual[key]:
            raise ValueError('Marginal diagnostics differ from aggregate')


def check_veto(actual, diag, divergences):
    reasons = ['divergent_transition'] if divergences else []
    if not math.isfinite(diag['rhat']) or diag['rhat'] > 1.01:
        reasons.append('rhat')
    for key in ['bulk_ess','tail_ess']:
        if not math.isfinite(diag[key]) or diag[key] < 400:
            reasons.append(key)
    if actual != {'eligible_for_calibration':not reasons,'veto_reasons':reasons,'scientific_acceptance':False}:
        raise ValueError('Absolute sampler veto differs')


def gaussian(spec, raw):
    result = raw['result']
    identity = result['identity']
    required = {'schema':'gaussian_hmc_v1','target':'centered_univariate_gaussian',
                'method':'leapfrog_metropolis_full_momentum_refresh','frequency':spec['frequency'],
                'step_size':spec['step_size'],'steps':spec['steps'],'warmup':8,
                'initial_positions':[-3.,-1.,1.,3.],'seed':12}
    if identity != required:
        raise ValueError('Gaussian kernel identity differs')
    h,w = Q(spec['step_size']),Q(spec['frequency'])
    step = [[1-h*h*w*w/2,h],[-h*w*w*(1-h*h*w*w/4),1-h*h*w*w/2]]
    matrix = [[Q(1),Q(0)],[Q(0),Q(1)]]
    for _ in range(spec['steps']):
        matrix = [[sum(matrix[i][k]*step[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    if matrix[0][0]*matrix[1][1]-matrix[0][1]*matrix[1][0] != 1 or matrix[0][0] != matrix[1][1]:
        raise ValueError('Gaussian determinant/reversibility identity differs')
    trace = result['checkpoint']['trace']
    if len(trace) != 40:
        raise ValueError('Incomplete Gaussian transition roster')
    positions,rng = [-3.,-1.,1.,3.],np.random.RandomState(12)
    divergences=accepted_count=0
    for index,record in enumerate(trace):
        if record['phase'] != ('warmup' if index<8 else 'retained') or len(record['transitions']) != 4:
            raise ValueError('Gaussian phase/chain roster differs')
        for j,row in enumerate(record['transitions']):
            q,p = Q(positions[j]),Q(float(rng.normal()))
            u = float(rng.uniform(np.nextafter(0.,1.),1.))
            qq,pp = matrix[0][0]*q+matrix[0][1]*p,matrix[1][0]*q+matrix[1][1]*p
            delta = (w*w*(qq*qq-q*q)+pp*pp-p*p)/2
            diverged = abs(delta)>1000
            accepted = not diverged and math.log(u)<min(0.,-float(delta))
            # Roundoff at the exact resonance may change an accept/reject only
            # if u is inside the tolerance band; these fixed draws are not.
            if row['accepted'] != accepted or row['diverged'] != diverged:
                raise ValueError('Metropolis decision/divergence differs')
            near(row['delta_energy'],float(delta))
            near(row['q'],float(qq)); near(row['p'],float(pp))
            near(row['acceptance_probability'], 1. if delta<=0 else math.exp(-float(delta)))
            near(row['next_q'],float(qq if accepted else q))
            near(row['next_p'],float(-pp if accepted else p))
            positions[j]=row['next_q']
            if index>=8:
                near(result['chains'][j][index-8][0],positions[j])
            divergences+=int(diverged); accepted_count+=int(accepted)
    work = 40*4*2*spec['steps']
    expected_increment = (16 if spec.get('resume') else 40)*4*2*spec['steps']
    checkpoint=result['checkpoint']
    body={k:v for k,v in checkpoint.items() if k!='binding'}
    binding=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if (checkpoint['binding']!=binding or checkpoint['positions']!=positions or checkpoint['completed_draws']!=32
            or result['gradient_evaluations']!=work or checkpoint['gradient_evaluations']!=work
            or result['incremental_gradient_evaluations']!=expected_increment
            or result['divergences']!=divergences or result['accepted']!=accepted_count):
        raise ValueError('Gaussian state/work accounting differs')
    random_state=rng.get_state()
    if checkpoint['rng_state'] != [random_state[0],random_state[1].tolist(),*random_state[2:]]:
        raise ValueError('Gaussian terminal RNG differs')
    if spec.get('resume'):
        partial=raw['partial']
        if (partial['checkpoint']['trace']!=trace[:24] or partial['gradient_evaluations']!=24*4*2*spec['steps']
                or partial['incremental_gradient_evaluations']!=partial['gradient_evaluations']):
            raise ValueError('Gaussian resume repeated/omitted physical work')
    elif raw['partial'] is not None:
        raise ValueError('Unexpected sampler recovery')
    expected=diagnostics(result['chains'])
    check_diagnostics(result['diagnostics'],expected)
    check_veto(result['veto'],expected,divergences)
    if spec['id']=='resonance':
        for chain,initial in zip(result['chains'],required['initial_positions']):
            near([x[0]**2 for x in chain],[initial**2]*32)
    return {'gradient_evaluations':work,'divergences':divergences,'accepted':accepted_count,
            'calibration_claim':False}


def diagnostic_boundaries(raw):
    if len(raw['boundaries'])!=6 or len(raw['fixtures'])!=2:
        raise ValueError('Diagnostic adverse inventory differs')
    for row in raw['boundaries']:
        diag={k:float(v) for k,v in row['diagnostics'].items()}
        check_veto(row['veto'],diag,row['divergences'])
    for fixture in raw['fixtures']:
        check_diagnostics(fixture['diagnostics'],diagnostics(fixture['chains']))
    return {'boundary_cases':6,'diagnostic_fixtures':2}


def verify_slot(spec, raw):
    kind=spec['kind']
    if kind=='trust':
        from validation.trust_reference import verify
    elif kind=='multifidelity':
        from validation.multifidelity_reference import verify
    elif kind=='priorband':
        if 'product_transform' in spec:
            from validation.product_prior_reference import verify
        else:
            from validation.prior_reference import verify
    elif kind=='cost':
        from validation.cost_acceptance import summarize
        report=summarize(spec['profile'],raw['observations'])
        if raw['error'] is not None or raw['failed_attempt'] is not None or report['status']!='complete':
            return {'status':'INCONCLUSIVE'}
        if report!=raw['summary']:
            raise ValueError('Cost finite summary differs')
        return report
    else:
        return {'vector':vector,'pibo':pibo,'advisory':advisory,'gaussian':gaussian,
                'diagnostics':lambda spec,raw:diagnostic_boundaries(raw)}[kind](spec,raw)
    return verify(raw)
