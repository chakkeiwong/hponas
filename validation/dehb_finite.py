"""Finite native DEHB evidence: spectral updates and original method traces."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import time

import numpy as np

from hponas import DEHBController, SearchSpace, Knob, LocalExecutor
from hponas.persistence import atomic_json
from validation.evidence import ROOT, digest, source_digest
from validation.population_campaign import write_new, binding, read_binding
from validation.tier1_campaign import require_runtime
from validation.stylized_campaign import bounded_seconds

CLAIM = 'finite_native_dehb_conformance_v1'


def contract():
    return {'entry': 'V07', 'version': 1, 'claim': CLAIM,
        'slots': [{'id': f'{name}-{seed}', 'initial': initial, 'seed': seed}
                  for name, initial in [('late', [.1, 1.]), ('early', [1., .1]), ('balanced', [1., 1.])]
                  for seed in [0, 1]],
        'jobs_per_slot': 50, 'fidelities': [1, 2, 4, 8], 'eta': 2,
        'mutation_factor': .5, 'crossover_probability': .5,
        'reference_commit': '58f9fb9045e63530692adc6306fc297e318f11f2',
        'model': 'Q diag(1,3) Q^T; Q=[[3/5,-4/5],[4/5,3/5]]; eta=1/40+3x/5',
        'evaluation': 'restart at each fidelity; every gradient update charged',
        'selection': 'minimum full-fidelity loss, earliest evaluation breaks ties',
        'recovery': 'after jobs 7 and 21 and pending asks 13 and 37; exact native JSON transcript',
        'absolute_tolerance': 2e-12, 'relative_tolerance': 2e-10,
        'reference_coordinate_tolerance': 1e-15,
        'decision': 'all six complete known-answer and pinned-reference trajectories conform',
        'inference': 'none; regret descriptive; no method superiority or default',
        'allocation': {'generation': 1, 'reconstructions': 3, 'processes': 2,
            'wall_seconds_per_process': 300, 'maximum_phase_seconds': 600,
            'cpu_affinity_count': 1, 'numerical_threads': 1, 'gpu': False,
            'maximum_gradient_updates': 2400, 'reconstruction_gradient_updates': 0},
        'pass': 'Finite opt-in native DEHB only; no general superiority/default/integrated release.',
        'fail': 'Withhold DEHB acceptance; retain failure and repair prospectively.',
        'inconclusive': 'Withhold DEHB acceptance; preserve consumed slots and partial work.'}


def space():
    return SearchSpace([Knob('x', 'continuous', (0., 1.))])


def options(seed):
    return dict(seed=seed, min_fidelity=1, max_fidelity=8, eta=2,
                mutation_factor=.5, crossover_probability=.5)


def execute_slot(slot, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    initial = np.asarray(slot['initial'])
    q = np.array([[.6, -.8], [.8, .6]])
    h = q @ np.diag([1., 3.]) @ q.T
    controller = DEHBController(space(), **options(slot['seed']))
    trace, recoveries = [], []
    executor = LocalExecutor()
    for index in range(contract()['jobs_per_slot']):
        trial = controller.ask()
        if index in [13, 37]:
            path = directory / f'pending-{index}.json'
            atomic_json(path, controller.state_dict())
            other = DEHBController(space(), **options(slot['seed']))
            other.load_state_dict(json.loads(path.read_text()))
            if other.ask().to_dict() != trial.to_dict():
                raise ValueError('Pending native DEHB trial changed on recovery')
            controller = other
            recoveries.append({'boundary': index, 'kind': 'pending', 'state': json.loads(path.read_text())})
        updates = []
        def objective(values, fidelity):
            state = q @ initial
            eta = .025 + .6 * values['x']
            for step in range(1, int(fidelity) + 1):
                state -= eta * (h @ state)
                updates.append({'step': step, 'state': state.tolist(),
                                'loss': float(state @ state / (initial @ initial))})
            return {'value': updates[-1]['loss'], 'cost': int(fidelity)}
        job = deepcopy(controller.pending)
        result = executor.execute(trial, objective)
        controller.tell(result)
        trace.append({'job': job, 'updates': updates, 'result': controller.history[-1]['result']})
        if index in [7, 21]:
            path = directory / f'committed-{index}.json'
            atomic_json(path, controller.state_dict())
            other = DEHBController(space(), **options(slot['seed']))
            other.load_state_dict(json.loads(path.read_text()))
            controller = other
            recoveries.append({'boundary': index, 'kind': 'committed', 'state': json.loads(path.read_text())})
    executor.shutdown()
    return {'slot': slot, 'trace': trace, 'recoveries': recoveries, 'best': controller.best(),
            'state': controller.state_dict(), 'gradient_updates': sum(len(r['updates']) for r in trace)}


def _close(actual, expected, atol=2e-12, rtol=2e-10):
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.allclose(a, b, atol=atol, rtol=rtol):
        raise ValueError('DEHB spectral reconstruction differs')


def verify_raw(slot, raw):
    if raw['slot'] != slot or len(raw['trace']) != 50:
        raise ValueError('DEHB complete fixed roster differs')
    history, work, expected_recoveries = [], 0, []
    for index, row in enumerate(raw['trace']):
        job, result = row['job'], row['result']
        f, x = job['fidelity'], job['values']['x']
        if f not in [1., 2., 4., 8.] or not 0 <= x <= 1 or job['config'] != [x]:
            raise ValueError('DEHB coordinate or fidelity differs')
        if job['trial_id'] != f"dehb_{slot['seed']}_{index}":
            raise ValueError('DEHB trial identity differs')
        if index in [13, 37]:
            expected_recoveries.append({'boundary': index, 'kind': 'pending',
                'state': {'schema': 'serial_dehb_v1', 'space': space().to_dict(),
                    'options': options(slot['seed']), 'history': deepcopy(history), 'pending': job}})
        if len(row['updates']) != f:
            raise ValueError('DEHB physical update count differs')
        eta = 1/40 + 3*x/5
        for step, update in enumerate(row['updates'], 1):
            if update['step'] != step:
                raise ValueError('DEHB skipped/repeated update')
            a, b = slot['initial'][0]*(1-eta)**step, slot['initial'][1]*(1-3*eta)**step
            state = [3*a/5-4*b/5, 4*a/5+3*b/5]
            loss = (a*a+b*b) / sum(v*v for v in slot['initial'])
            _close(update['state'], state); _close(update['loss'], loss)
        expected = {'trial_id': job['trial_id'], 'objective_value': row['updates'][-1]['loss'],
                    'cost': float(f), 'fidelity': f, 'status': 'completed'}
        if result != expected:
            raise ValueError('DEHB result/report accounting differs')
        history.append({'job': job, 'result': result})
        work += int(f)
        if index in [7, 21]:
            expected_recoveries.append({'boundary': index, 'kind': 'committed',
                'state': {'schema': 'serial_dehb_v1', 'space': space().to_dict(),
                    'options': options(slot['seed']), 'history': deepcopy(history), 'pending': None}})
    expected_state = {'schema': 'serial_dehb_v1', 'space': space().to_dict(),
        'options': options(slot['seed']), 'history': history, 'pending': None}
    if raw['state'] != expected_state or raw['recoveries'] != expected_recoveries:
        raise ValueError('DEHB retained recovery transcript differs')
    best = min((r for r in history if r['job']['fidelity'] == 8), key=lambda r: r['result']['objective_value'])
    if raw['best'] != best or raw['gradient_updates'] != work:
        raise ValueError('DEHB final selection or total physical work differs')
    a, b = slot['initial']
    r = (a*a/(3*b*b))**(1/15)
    eta_star = (1+r)/(3+r)
    optimum = (a*a*(1-eta_star)**16+b*b*(1-3*eta_star)**16)/(a*a+b*b)
    value = best['result']['objective_value']
    if value < optimum - 2e-12:
        raise ValueError('DEHB result falls below the mathematical optimum')
    return {'slot': slot['id'], 'gradient_updates': work, 'selected_loss': value,
            'optimal_eta': eta_star, 'optimal_loss': optimum, 'regret': value - optimum}


def require_phase():
    from tools.program_state import canonical_digest
    p = json.loads((ROOT / 'docs/program/program.json').read_text())
    if next(d for d in p['decisions'] if d['id'] == 'D-PROTOCOL-T3-ACCEPTANCE')['status'] != 'accepted':
        raise ValueError('Tier-3 acceptance is not frozen')
    if next(s for s in p['continuation']['steps'] if s['id'] == 'T3-01/ACCEPTANCE-FREEZE')['state'] != 'complete':
        raise ValueError('Tier-3 phase is not complete')
    eid = p['protocol_phase_bindings'].get('tier3-acceptance')
    row, = [e for e in p['evidence'] if e['id'] == eid]
    path = ROOT / row['path']
    if digest(path) != row['sha256']: raise ValueError('DEHB phase changed')
    phase = json.loads(path.read_text())
    registry = json.loads((ROOT / 'validation/protocols.json').read_text())
    if (phase['kind'] != 'dehb_finite_phase_v1' or phase['source_digest'] != source_digest()
            or phase['runtime'] != require_runtime() or phase['contract'] != contract()
            or phase['registry_sha256'] != digest(ROOT / 'validation/protocols.json')
            or phase['entry_sha256'] != canonical_digest(registry['entries']['V07'])
            or registry['entries']['V07'].get('contract') != contract()
            or phase['protocol_sha256'] != digest(ROOT / 'validation/protocols/v07_protocol.md')
            or phase['resource_authorization'] != 'standing_user_bounded_local_known_answer_execution'):
        raise ValueError('DEHB frozen source/runtime/protocol/allocation differs')
    for item in phase['external_files']:
        file = (ROOT / item['path']).resolve()
        if not file.is_relative_to(ROOT) or digest(file) != item['sha256']:
            raise ValueError('DEHB external reference changed')
    name = phase['run_name']
    if not isinstance(name, str) or name in {'', '.', '..'} or Path(name).name != name:
        raise ValueError('Unsafe DEHB run name')
    return {**binding(path), 'run_path': str((ROOT / 'validation/artifacts/V07' / name).resolve()),
            'reference': str((ROOT / phase['reference']).resolve())}


def campaign(directory):
    directory = Path(directory).resolve()
    phase = require_phase()
    if str(directory) != phase['run_path']: raise ValueError('Unallocated DEHB run')
    write_new(directory / 'freeze.json', {'phase': phase, 'contract': contract(), 'source_digest': source_digest()})
    write_new(directory / 'generation-start.json', {'created_utc': datetime.now(timezone.utc).isoformat()})
    started = time.monotonic()
    records = []
    error = None
    try:
        with bounded_seconds(300):
            for i, slot in enumerate(contract()['slots']):
                write_new(directory / f'slot-{i:02d}-start.json', {'slot': slot})
                raw = execute_slot(slot, directory / f'slot-{i:02d}')
                write_new(directory / f'raw-{i:02d}.json', raw)
                records.append(binding(directory / f'raw-{i:02d}.json'))
    except Exception as exc:
        error = {'type': type(exc).__name__, 'message': str(exc),
                 'completed_slots': len(records), 'partial_work': 'retained; never retried'}
        write_new(directory / 'generation-error.json', error)
    return {'schema_version': 1, 'validation_id': 'V07', 'claim': CLAIM, 'run_dir': str(directory),
        'freeze': binding(directory / 'freeze.json'), 'records': records,
        'generation_complete': error is None, 'generation_error': error,
        'generation_seconds': time.monotonic()-started}


def reconstruct(result):
    if result.get('claim') != CLAIM or result.get('schema_version') != 1 or result.get('validation_id') != 'V07':
        raise ValueError('Unknown finite DEHB schema')
    directory = Path(result['run_dir']).resolve()
    phase = require_phase()
    if str(directory) != phase['run_path']: raise ValueError('Unallocated DEHB run')
    for i in range(1, 4):
        try:
            write_new(directory / f'reconstruction-{i:02d}-start.json', {'created_utc': datetime.now(timezone.utc).isoformat()})
            break
        except FileExistsError: pass
    else: raise ValueError('DEHB reconstruction allocation exhausted')
    try:
        with bounded_seconds(300):
            expected = {'phase': phase, 'contract': contract(), 'source_digest': source_digest()}
            if read_binding(result['freeze'], directory) != expected:
                raise ValueError('DEHB freeze differs')
            if result.get('generation_complete') is not True:
                # Preserve an interrupted generation as incomplete evidence;
                # never dispatch the objective from the reconstruction path.
                report = {'verdict': 'INCONCLUSIVE', 'complete': False,
                          'reason': 'Retained DEHB generation is incomplete',
                          'error': result.get('generation_error')}
                write_new(directory / f'reconstruction-{i:02d}-result.json', report)
                return report
            if len(result['records']) != 6:
                raise ValueError('DEHB roster differs')
            seconds = result['generation_seconds']
            if type(seconds) not in (float, int) or not math.isfinite(seconds) or not 0 <= seconds <= 300:
                raise ValueError('DEHB generation exceeded its allocation')
            spec = importlib.util.spec_from_file_location('frozen_dehb_reference', phase['reference'])
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            reports = []
            for index, (slot, item) in enumerate(zip(contract()['slots'], result['records'])):
                raw = read_binding(item, directory)
                report = verify_raw(slot, raw)
                data = directory / f'slot-{index:02d}'
                names = {f"{r['kind']}-{r['boundary']}.json" for r in raw['recoveries']}
                if {p.name for p in data.iterdir()} != names:
                    raise ValueError('DEHB checkpoint inventory differs')
                for recovery in raw['recoveries']:
                    path = data / f"{recovery['kind']}-{recovery['boundary']}.json"
                    if json.loads(path.read_text()) != recovery['state']:
                        raise ValueError('DEHB checkpoint bytes differ from raw record')
                module.verify_jobs(raw)
                reports.append(report)
            report = {'verdict': 'PASS', 'complete': True, 'reports': reports,
                      'source_digest': source_digest(), 'integrated_release_accepted': False}
    except TimeoutError as exc:
        report = {'verdict': 'INCONCLUSIVE', 'complete': False, 'reason': str(exc)}
    except (ValueError, KeyError, TypeError, IndexError, OSError, AssertionError) as exc:
        report = {'verdict': 'FAIL', 'complete': False, 'reason': f'{type(exc).__name__}: {exc}'}
    write_new(directory / f'reconstruction-{i:02d}-result.json', report)
    return report
