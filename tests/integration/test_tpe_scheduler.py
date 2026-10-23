"""Root identity and full-fidelity Optuna fitting, independently inspected."""
from copy import deepcopy
import json
import math

import optuna
import pytest

from hponas import Study, SearchSpace, Knob, LocalExecutor, Config, Trial, Result
from hponas.searchers_tpe import TPESearcher
from hponas.searchers.adapter import LegacySearcherAdapter
from hponas.schedulers import ASHAConfig, ASHAScheduler


def space():
    return SearchSpace([Knob('x', 'ordinal', (0, 1))])


def register(adapter, tid, config, fidelity=1., root=None):
    trial = Trial(config, tid, fidelity=fidelity, root_trial_id=root or tid)
    adapter.trials[tid] = config
    adapter.register_trial(trial)


def test_duplicate_configurations_and_reversed_results_keep_ask_identity():
    adapter = LegacySearcherAdapter(TPESearcher(space(), model_fidelity=2), maximize=False)
    configs = [adapter.suggest() for _ in range(4)]
    for i, config in enumerate(configs):
        register(adapter, str(i), config)
    assert len({tuple(c.values.items()) for c in configs}) < len(configs)
    for i in reversed(range(4)):
        adapter.observe(Result(str(i), -10000-i, 1., fidelity=1.))
    assert all(t.state == optuna.trial.TrialState.RUNNING for t in adapter.searcher._study.trials)
    for i in reversed(range(4)):
        register(adapter, str(i)+'-full', configs[i], 2., str(i))
        adapter.observe(Result(str(i)+'-full', 10+i, 1., fidelity=2.))
    assert [t.value for t in adapter.searcher._study.trials] == [10., 11., 12., 13.]
    assert len(adapter.history) == 8
    saved = json.loads(json.dumps(adapter.get_state()))
    restored = LegacySearcherAdapter(TPESearcher(space(), model_fidelity=2), maximize=False)
    restored.set_state(saved)
    assert restored.get_state() == adapter.get_state()
    assert restored.suggest() == adapter.suggest()


def test_failures_and_unpromoted_roots_never_enter_the_tpe_training_set():
    adapter = LegacySearcherAdapter(TPESearcher(space(), model_fidelity=2))
    for i in range(2):
        register(adapter, str(i), adapter.suggest())
    adapter.observe(Result('0', math.nan, 1., fidelity=1., status='failed'))
    adapter.observe(Result('1', 9000., 1., fidelity=1.))
    adapter.finalize_pending()
    assert not adapter.searcher._pending
    assert all(t.state == optuna.trial.TrialState.FAIL and t.value is None for t in adapter.searcher._study.trials)


def test_direct_ambiguous_ask_refusal_is_atomic():
    searcher = TPESearcher(space())
    configs = searcher.propose(8)
    repeated = next(c for c in configs if configs.count(c) > 1)
    before = deepcopy(searcher.state_dict())
    with pytest.raises(ValueError, match='supply trial_number'):
        searcher.observe({'config': repeated, 'value': 1.})
    assert searcher.state_dict() == before


def test_tpe_asha_recovery_matches_uninterrupted_root_and_result_ledgers(tmp_path):
    def objective(config, fidelity):
        return {'value': -1000*config['x'] if fidelity == 1 else 2+config['x'], 'cost': fidelity}
    def make(fn=objective):
        return Study(TPESearcher(space(), seed=4, model_fidelity=2), LocalExecutor(), fn,
            scheduler=ASHAScheduler(ASHAConfig(r_min=1, r_max=2, eta=2, promotion_policy='legacy_bootstrap')),
            budget=6, maximize=False, study_name='tpe-asha', checkpoint_dir=tmp_path,
            legacy_reason='Scheduler identity fixture; protected evaluation tested separately')
    uninterrupted = make()
    uninterrupted.run()
    calls = []
    def crash(config, fidelity):
        calls.append(1)
        if len(calls) == 3:
            raise KeyboardInterrupt('Before third commit')
        return objective(config, fidelity)
    interrupted = make(crash)
    with pytest.raises(KeyboardInterrupt):
        interrupted.run()
    resumed = make()
    resumed.load_checkpoint(tmp_path/'tpe-asha_checkpoint.json')
    resumed.run()
    project = lambda s: [(r.trial_id, r.fidelity, r.objective_value, r.status) for r in s.get_history()]
    assert project(resumed) == project(uninterrupted)
    assert resumed.searcher.searcher.state_dict() == uninterrupted.searcher.searcher.state_dict()
    complete = [t for t in resumed.searcher.searcher._study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    assert complete and all(t.value in (2., 3.) for t in complete)
    assert not resumed.searcher.searcher._pending
