"""Bounded physical producers for the exposed Tier-1 corpus.

Numerical decisions live in tier1_reference, separately from these producers.
Retained example APIs remain development APIs; official identity comes from the
frozen contract and campaign driver, never an example's printed acceptance flag.
"""
from copy import deepcopy
import json
import math
from pathlib import Path


def write_new(path, value):
    import os
    with Path(path).open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def portable(value):
    """JSON explicitly represents nonfinite *diagnostics*, never numerical data."""
    if isinstance(value, float) and not math.isfinite(value):
        return 'Infinity' if value > 0 else '-Infinity' if value < 0 else 'NaN'
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [portable(v) for v in value]
    return value


class QuadraticAdvice:
    """Analytically normalized score under uniform eta in [.025,.625]."""
    def __init__(self, center):
        self.center = center

    def __call__(self, config):
        width = .12
        mass = width*math.sqrt(math.pi)/1.2*(
            math.erf((.625-self.center)/width)-math.erf((.025-self.center)/width))
        return math.exp(-((config['eta']-self.center)/width)**2)/mass


def pibo(spec, directory):
    from hponas import Knob, SearchSpace
    from hponas.priors import GuardedPrior
    from hponas.searchers_gp import GPqLogEISearcher
    from workloads.tuning_models import quadratic
    import torch
    space = SearchSpace([Knob('eta', 'continuous', (.025, .625))])
    prior = None if spec['advice'] == 'none' else GuardedPrior(
        QuadraticAdvice(spec['center']), space, normalize=False)
    def make(seed):
        return GPqLogEISearcher(space, seed=seed, prior_fn=prior,
                              n_fantasies=16, raw_samples=32, n_restarts=2, prior_beta=2.)
    searcher = make(spec['seed'])
    prefix = searcher.propose(3)
    observations, probes, boundary = [], [], None
    for index in range(spec['trials']):
        config = prefix[index] if index < 3 else searcher.propose(1)[0]
        if index >= 3 and prior is not None:
            # Probe the actual acquisition object used for this proposal.
            locations = torch.tensor([[[0.]], [[.5]], [[1.]]], dtype=torch.double)
            with torch.no_grad():
                base = searcher._acqf.base_acqf(locations).reshape(-1).tolist()
                weighted = searcher._acqf(locations).reshape(-1).tolist()
            probes.append({'observations': index, 'etas': [.025, .325, .625],
                           'base': base, 'weighted': weighted,
                           'guarded_scores': [prior({'eta': x}) for x in [.025, .325, .625]]})
        state, updates = None, []
        for step in range(1, 9):
            result = quadratic(config['eta'], step, state)
            state = result['checkpoint']
            updates.append({'step': step, 'value': result['value'], 'checkpoint': deepcopy(state)})
        row = {'config': config, 'value': result['value'], 'cost': 8, 'updates': updates}
        # Completed physical work survives a subsequent delivery failure.
        write_new(directory/f'physical-{index:03d}.json', row)
        observations.append(row)
        searcher.observe({'config': config, 'value': -row['value'], 'cost': 8})
        if index == 3:
            boundary = json.loads(json.dumps(searcher.state_dict()))
            restored = make(999)
            restored.load_state_dict(boundary)
            searcher = restored
    return {'spec': spec, 'observations': observations, 'probes': probes,
            'recovery_boundary': boundary, 'state': searcher.state_dict()}


MO_ADVISORY = {
    'objectives': [{'name': 'loss', 'direction': 'min', 'lower': 0., 'upper': 1.},
                   {'name': 'width', 'direction': 'min', 'lower': 0., 'upper': 4.}],
    'constraints': {'width': 2.}, 'work_unit': 'declared_steps',
    'r_min': 1, 'r_max': 4, 'eta': 2, 'selection': 'advisory',
}


def advisory(spec):
    from hponas.schedulers_mo import MultiObjectiveScheduler
    scheduler = MultiObjectiveScheduler(**MO_ADVISORY)
    events = []
    # A becomes worse; B improves. C is infeasible; D fails before promotion.
    for fidelity in [1, 2, 4]:
        for tid in (['A', 'B', 'C', 'D'] if fidelity == 1 else ['A', 'B']):
            loss = {'A': {1: .1, 2: .5, 4: .9}, 'B': {1: .9, 2: .5, 4: .1},
                    'C': {1: 0.}, 'D': {1: 0.}}[tid][fidelity]
            observation = scheduler.spec.observation(
                objectives=None if tid == 'D' else {'loss': loss, 'width': 3 if tid == 'C' else 1},
                constraints=None if tid == 'D' else {'width': 3 if tid == 'C' else 1}, work=fidelity,
                status='failed' if tid == 'D' else 'completed')
            decision = scheduler.report(tid, fidelity, observation)
            events.append({'kind': 'report', 'trial': tid, 'fidelity': fidelity,
                           'observation': observation, 'decision': decision})
        if spec['restore'] and fidelity == 1:
            saved = scheduler.state_dict()
            scheduler = MultiObjectiveScheduler(**MO_ADVISORY)
            scheduler.load_state_dict(saved)
        events.append({'kind': 'promote', 'fidelity': fidelity, 'promotions': scheduler.promote()})
    return {'contract': MO_ADVISORY, 'events': events, 'state': scheduler.state_dict()}


def gaussian(spec, directory):
    from workloads.gaussian_hmc import sample_gaussian
    controls = {k: spec[k] for k in ['step_size', 'steps', 'frequency']}
    controls.update(seed=12, warmup=8)
    partial = None
    if spec.get('resume'):
        partial = sample_gaussian(**controls, draws=16)
        write_new(directory/'partial.json', portable(partial))
    result = sample_gaussian(**controls, draws=32,
                             checkpoint=partial['checkpoint'] if partial else None)
    return portable({'result': result, 'partial': partial})


def diagnostic_boundaries():
    from workloads.gaussian_hmc import correctness_veto, chain_diagnostics
    rows = []
    for rhat, bulk, tail, divergences in [(1.01,400.,400.,0), (1.01001,400.,400.,0),
        (1.,399.,400.,0), (1.,400.,399.,0), (1.,400.,400.,1), (float('inf'),0.,0.,0)]:
        diag = {'rhat': rhat, 'bulk_ess': bulk, 'tail_ess': tail}
        rows.append({'diagnostics': diag, 'divergences': divergences,
                     'veto': correctness_veto(diag, divergences)})
    # Ties, odd lengths, folded scale disagreement and constant chains.
    chains = [[[float((i*(j+1)) % 7)] for i in range(17)] for j in range(4)]
    constant = [[[float(j)] for _ in range(16)] for j in range(4)]
    return portable({'boundaries': rows, 'fixtures': [
        {'chains': c, 'diagnostics': chain_diagnostics(c)} for c in [chains, constant]]})


def execute_slot(spec, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    kind, name = spec['kind'], spec['id']
    options = {k: v for k, v in spec.items() if k not in {'id', 'kind'}}
    if kind == 'trust':
        from examples.trust_tuning import run_one
        run_one(directory, name, **options)
    elif kind == 'multifidelity':
        from examples.multifidelity_tuning import run_one, orders
        options['order'] = orders()[options['order']]
        run_one(directory, name, **options)
    elif kind == 'priorband':
        from examples.prior_tuning import run_one
        run_one(directory, name, **options)
    elif kind == 'vector':
        from examples.multi_objective_tuning import run
        raw = run(spec['method'], directory, spec['trials'])
        return {'observations': raw, 'snapshot': json.loads(
            (directory/(spec['method']+'_checkpoint.json')).read_text())}
    elif kind == 'pibo':
        return pibo(spec, directory)
    elif kind == 'advisory':
        return portable(advisory(spec))
    elif kind == 'gaussian':
        return gaussian(spec, directory)
    elif kind == 'diagnostics':
        return diagnostic_boundaries()
    elif kind == 'cost':
        from validation.cost_replay import run_slot
        return run_slot(spec['profile'], spec['seed'], spec['method'])
    else:
        raise ValueError('Unknown producer kind')
    return json.loads((directory/name/'raw.json').read_text())
