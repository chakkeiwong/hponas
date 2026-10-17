"""Execute pinned original NePS policy methods, without the vendor runtime."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from hponas.prior_band import PriorBand, bracket_widths
from hponas.schedulers_prior import PriorBandScheduler


@pytest.fixture(scope='module')
def vendor():
    base = Path(__file__).resolve().parents[1] / 'fixtures/neps_priorband_3f7475b'
    manifest = json.loads((base/'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((base/name).read_bytes()).hexdigest() == expected
    namespace = {'np': np, 'pd': pd, 'SearchSpace': object,
                 'compute_scores': lambda config, prior, inc: config}
    tree = ast.parse((base/'priorband.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PriorBandBase')
    names = {'find_incumbent', 'is_activate_inc', 'calc_sampling_args', 'set_sampling_weights_and_inc',
             '_prior_to_incumbent_ratio_constant', '_prior_to_incumbent_ratio_dynamic', 'prior_to_incumbent_ratio'}
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    util = ast.parse((base/'utils.py').read_text())
    resource = next(n for n in util.body if isinstance(n, ast.FunctionDef) and n.name == 'calc_total_resources_spent')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[resource, cls], type_ignores=[])), 'pinned-priorband', 'exec'), namespace)
    exec(compile((base/'promotion_policy.py').read_text(), 'pinned-promotions', 'exec'), namespace)
    tree = ast.parse((base/'successive_halving.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SuccessiveHalvingBase')
    cls.bases = []
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {'_get_config_map', '_get_rung_map'}]
    namespace['IntegerParameter'] = type('IntegerParameter', (), {})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), 'pinned-brackets', 'exec'), namespace)
    return namespace


def policy(vendor, rows):
    obj = vendor['PriorBandBase']()
    obj.eta = 3
    obj.rung_map, obj.config_map = {0: 1, 1: 3, 2: 9}, {0: 9, 1: 3, 2: 1}
    obj.min_rung, obj.max_rung = 0, 2
    obj.inc_style, obj.prior_weight_type, obj.inc_sample_type = 'constant', 'geometric', 'mutation'
    obj.inc_mutation_rate, obj.inc_mutation_std = .5, .25
    obj.observed_configs = pd.DataFrame(rows, columns=['rung', 'perf', 'config'])
    obj.rung_histories = {r: {'config': [], 'perf': []} for r in range(3)}
    for i, (rung, perf, _) in enumerate(rows):
        if np.isfinite(perf):
            obj.rung_histories[rung]['config'].append(i)
            obj.rung_histories[rung]['perf'].append(perf)
    obj.pipeline_space = SimpleNamespace(sample_default_configuration=lambda: 'prior')
    return obj


@pytest.mark.parametrize('rungs,finite', [([2, 2, 0, 0], [True]*4), ([2, 2, 1], [True]*3),
                                          ([2, 2, 1, 0], [True]*4), ([1]*7, [True]*7),
                                          ([2, 2, 1], [True, True, False])])
def test_activation_matches_original_boundary(vendor, rungs, finite):
    band = PriorBand(rungs=[1, 3, 9], eta=3)
    rows = []
    for i, (rung, ok) in enumerate(zip(rungs, finite)):
        band.observe(str(i), rung=3**rung, value=i if ok else None, work=0,
                     status='completed' if ok else 'failed')
        rows.append((rung, i if ok else np.nan, str(i)))
    reference = policy(vendor, rows)
    assert band.can_activate() == bool(reference.is_activate_inc())
    assert band.incumbent() == reference.find_incumbent()


@pytest.mark.parametrize('kind', ['geometric', 'linear', '50-50'])
@pytest.mark.parametrize('active', [False, True])
def test_mixture_weights_at_every_start_rung(vendor, kind, active):
    rungs = [2, 2, 1] if active else [0]
    band = PriorBand(rungs=[1, 3, 9], eta=3)
    rows = []
    for i, rung in enumerate(rungs):
        band.observe(str(i), rung=3**rung, value=i, work=0)
        rows.append((rung, i, str(i)))
    reference = policy(vendor, rows)
    reference.prior_weight_type = kind
    for rung in range(3):
        expected = reference.set_sampling_weights_and_inc(rung)['weights']
        assert {k: float(v) for k, v in band.sampling_weights(rung, prior_weight_type=kind).items()} == pytest.approx(expected, abs=1e-15)


@pytest.mark.parametrize('size', [0, 2, 3, 8, 12])
@pytest.mark.parametrize('rung', [0, 1, 2])
def test_dynamic_top_set_and_sparse_rung_fallback(vendor, size, rung):
    scores = [(i+1, (i+1)**2+1) for i in range(size)]
    rows = [(rung, size-i, pair) for i, pair in enumerate(scores)]
    reference = policy(vendor, rows)
    band = PriorBand(rungs=[1, 3, 9], eta=3)
    for i, (_, loss, _) in enumerate(rows):
        band.observe(str(i), rung=3**rung, value=loss, work=0)
    actual = band.prior_to_incumbent_ratio(style='dynamic', scores={str(i): p for i, p in enumerate(scores)})
    assert tuple(map(float, actual)) == pytest.approx(reference._prior_to_incumbent_ratio_dynamic(2), abs=1e-15)


@pytest.mark.parametrize('eta,count', [(2, 4), (3, 3), (4, 4)])
def test_bracket_widths_and_fixed_promotions_match_pinned_neps(vendor, eta, count):
    reference = vendor['SuccessiveHalvingBase']()
    reference.eta, reference.min_budget, reference.max_budget = eta, 1, eta**(count-1)
    reference.stopping_rate_limit = count-1
    reference.pipeline_space = SimpleNamespace(fidelity=SimpleNamespace())
    scheduler = PriorBandScheduler(rungs=[eta**i for i in range(count)], eta=eta)
    serial = 0
    for start in range(count):
        width_map = reference._get_config_map(start)
        assert bracket_widths(count, eta, start) == list(width_map.values())
        roots = []
        for _ in range(width_map[start]):
            tid = f'root-{serial}'
            serial += 1
            assert scheduler.register_trial(tid) == eta**start
            roots.append(tid)
        for rung in range(start, count):
            for i, tid in enumerate(roots):
                scheduler.report(tid, eta**rung, float(len(roots)-i))
            if rung == count-1:
                for tid in roots:
                    scheduler.finish(tid, 'completed')
                assert scheduler.promote() == []
                break
            ref = vendor['SyncPromotionPolicy'](eta)
            members = {r: np.array([], dtype=str) for r in width_map}
            perfs = {r: np.array([]) for r in width_map}
            members[rung] = np.array(roots)
            perfs[rung] = np.array([float(len(roots)-i) for i in range(len(roots))])
            ref.set_state(max_rung=count-1, members=members, performances=perfs, config_map=width_map)
            expected = list(ref.retrieve_promotions()[rung])
            assert scheduler.promote() == [(tid, eta**(rung+1)) for tid in expected]
            assert scheduler.promote() == []
            roots = expected
        state = json.loads(json.dumps(scheduler.state_dict()))
        restored = PriorBandScheduler(rungs=[eta**i for i in range(count)], eta=eta)
        restored.load_state_dict(state)
        scheduler = restored
