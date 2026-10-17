"""Prior sampling through actual Study, Store and synchronous allocation."""
from copy import deepcopy
from fractions import Fraction as Q
import json
import pytest

from hponas import Knob, SearchSpace, Result, FinitePriorSearcher, PriorPendingError
from hponas import PriorBandScheduler, Study, LocalExecutor
from hponas.store import Store


def searcher(cap=1, seed=0, **kwargs):
    return FinitePriorSearcher(SearchSpace([Knob('cell', 'ordinal', (0, 1))]),
                               [{'cell': 0}, {'cell': 1}], [3, 1], Q(1, 2),
                               seed=seed, max_proposals=cap, **kwargs)


def objective(config, fidelity=1, resume_from=0, checkpoint=None, reporter=None, **kwargs):
    if resume_from:
        assert checkpoint == {'step': resume_from}
    value = float(config['cell'])
    for step in range(int(resume_from) + 1, int(fidelity) + 1):
        reporter(step, value, cost=step - resume_from, checkpoint={'step': step})
    return {'value': value, 'cost': fidelity - resume_from,
            'checkpoint': {'step': fidelity}}


def test_finite_prior_searcher_recovery_never_invents_trial_ids():
    first = searcher()
    outputs, pending = [], 0
    for i in range(40):
        try:
            config = first.suggest()
        except PriorPendingError:
            state = json.loads(json.dumps(first.get_state()))
            restored = searcher(seed=55)
            restored.set_state(state)
            first = restored
            pending += 1
            continue
        tid = f'public-{i}'
        assert tid not in first.trials
        first.trials[tid] = config
        first.observe(Result(tid, float(config.values['cell'])))
        outputs.append(config.values['cell'])
    assert outputs and pending
    with pytest.raises(ValueError):
        first.observe(Result('unbound', 0))


@pytest.mark.parametrize('workers', [1, 3])
def test_study_checkpoints_pending_draw_and_store_recovery(tmp_path, workers):
    baseline = Study(searcher(1000), LocalExecutor(), objective, budget=25,
                     study_name='prior', maximize=False, max_concurrent=workers)
    expected = baseline.run()
    store = Store(tmp_path/'prior.sqlite')
    interruptions = 0
    for attempt in range(200):
        target = Study(searcher(), LocalExecutor(), objective, budget=25,
                       study_name='prior', maximize=False, max_concurrent=workers,
                       store=store, checkpoint_dir=tmp_path)
        if attempt:
            target.load_checkpoint()
        try:
            outcome = target.run()
        except PriorPendingError:
            interruptions += 1
            state = store.load_study_snapshot('prior')
            assert state['searcher_state']['prior']['pending_prior']
            assert not state['finished']
            assert state['n_suggested'] == len(state['trials'])
            assert json.loads((tmp_path/'prior_checkpoint.json').read_text()) == state
        else:
            break
    else:
        pytest.fail('Local proposal bound exhausted')
    assert interruptions > 0
    assert outcome.best_value == expected.best_value
    assert [t.config.to_dict() for t in target.trials.values()] == [t.config.to_dict() for t in baseline.trials.values()]
    assert target.searcher._sampler.state_dict() == baseline.searcher._sampler.state_dict()
    assert len(target.searcher.history) == 25 and outcome.total_cost == 25
    store.close()


@pytest.mark.parametrize('damage', [lambda s: s['draws'].append(0),
                                    lambda s: s['trials']['public']['values'].update(cell=1-s['trials']['public']['values']['cell']),
                                    lambda s: s['history'].append(deepcopy(s['history'][0])),
                                    lambda s: s['support']['cells'].reverse()])
def test_searcher_rejects_inconsistent_restoration_atomically(damage):
    target = searcher(1000)
    config = target.suggest()
    target.trials['public'] = config
    target.observe(Result('public', float(config['cell'])))
    before = target.get_state()
    bad = deepcopy(before)
    damage(bad)
    with pytest.raises(ValueError):
        target.set_state(bad)
    assert target.get_state() == before


def test_support_identity_binds_order_base_measure_and_conditions():
    space = SearchSpace([Knob('branch', 'categorical', ['off', 'on']),
                         Knob('rate', 'continuous', (1., 4.), transform='log', condition=('branch', 'on'))])
    cells = [{'branch': 'off'}, {'branch': 'on', 'rate': 1.5}, {'branch': 'on', 'rate': 3.}]
    target = FinitePriorSearcher(space, cells, [1, 0, 4], Q(1, 2), base=[Q(1, 2), Q(1, 4), Q(1, 4)],
                                 cell_identity='half-off-half-log-rate-split-at-2')
    from hponas.prior_sampling import guarded_probabilities
    assert guarded_probabilities(target._sampler.base, target._sampler.weights, Q(1, 2)) == (Q(5, 12), Q(1, 8), Q(11, 24))
    changed = FinitePriorSearcher(space, cells, [1, 0, 4], Q(1, 2))
    with pytest.raises(ValueError):
        changed.set_state(target.get_state())
    for bad in [cells+cells[:1], [{'branch': 'off', 'rate': 1.5}], [{'branch': 'off', 'extra': 4}]]:
        with pytest.raises(ValueError):
            FinitePriorSearcher(space, bad, [1]*len(bad), Q(1, 2))


def test_synchronous_scheduler_waits_for_all_slots_and_never_promotes_losers():
    scheduler = PriorBandScheduler(rungs=[1, 3, 9], eta=3)
    for i in range(9):
        assert scheduler.register_trial(str(i)) == 1
    for i in range(8):
        scheduler.report(str(i), 1, 8-i)
    assert scheduler.promote() == []
    scheduler.report('8', 1, 0)
    assert scheduler.promote() == [('8', 3), ('7', 3), ('6', 3)]
    assert scheduler.promote() == []
    scheduler.report('8', 3, 2)
    assert scheduler.promote() == []
    scheduler.report('7', 3, 1)
    scheduler.finish('6', 'failed')
    assert scheduler.promote() == [('7', 9)]
    scheduler.report('7', 9, 0)
    scheduler.finish('7', 'completed')
    assert all(scheduler.promote() == [] for _ in range(10))
    state = json.loads(json.dumps(scheduler.state_dict()))
    restored = PriorBandScheduler(rungs=[1, 3, 9], eta=3)
    restored.load_state_dict(state)
    assert restored.state_dict() == state
    bad = deepcopy(state)
    bad['events'][-2]['value'] = 5
    with pytest.raises(ValueError):
        restored.load_state_dict(bad)
    assert restored.state_dict() == state


def test_hyperband_cycles_use_bracket_start_fidelity_and_store(tmp_path):
    store = Store(tmp_path/'band.sqlite')
    study = Study(searcher(1000), LocalExecutor(), objective, budget=15, maximize=False,
                  scheduler=PriorBandScheduler(rungs=[1, 3, 9], eta=3), store=store,
                  checkpoint_dir=tmp_path, study_name='band', continuation='resume')
    result = study.run()
    roots = [t for t in study.trials.values() if not t.parent_trial_id]
    assert [t.fidelity for t in roots] == [1]*9+[3]*3+[9]*3
    assert result.n_trials == 20 and result.total_cost == 63
    resumed = Study(searcher(1000), LocalExecutor(), objective, budget=15, maximize=False,
                    scheduler=PriorBandScheduler(rungs=[1, 3, 9], eta=3), store=store,
                    study_name='band', continuation='resume')
    resumed.load_checkpoint()
    assert resumed.run().n_trials == 20
    assert store.load_study_snapshot('band')['scheduler_state'] == study.scheduler.state_dict()
    store.close()


def test_pending_draws_and_hyperband_promotions_replay_exactly(tmp_path):
    from hponas.events import EventLog
    from hponas.replay import ReplayEngine
    log = EventLog(tmp_path/'events.jsonl')
    store = Store(tmp_path/'replay.sqlite')
    for attempt in range(100):
        study = Study(searcher(), LocalExecutor(), objective, budget=15, maximize=False,
                      scheduler=PriorBandScheduler(rungs=[1, 3, 9], eta=3), store=store,
                      event_log=log, study_name='replay', continuation='resume')
        if attempt:
            study.load_checkpoint()
        try:
            study.run()
        except PriorPendingError:
            continue
        break
    else:
        pytest.fail('No completion within diagnostic cap')
    engine = ReplayEngine(searcher(), log, seed=0,
                          scheduler=PriorBandScheduler(rungs=[1, 3, 9], eta=3))
    passed, message, _, _ = engine.verify_determinism(15)
    assert passed, message
    assert engine.searcher._sampler.state_dict() == study.searcher._sampler.state_dict()
    assert engine.scheduler.state_dict() == study.scheduler.state_dict()
    store.close()


@pytest.mark.parametrize('damage', ['searcher', 'scheduler'])
def test_recovery_joins_searcher_scheduler_and_study_ledgers(tmp_path, damage):
    study = Study(searcher(1000), LocalExecutor(), objective, budget=15, maximize=False,
                  scheduler=PriorBandScheduler(rungs=[1, 3, 9], eta=3), study_name='cross')
    study.run()
    before = deepcopy(study._snapshot())
    bad = deepcopy(before)
    if damage == 'searcher':
        bad['results']['cross_trial_0']['objective_value'] += 1
    else:
        bad['trials']['cross_trial_0']['fidelity'] = .5
    path = tmp_path/'bad.json'
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        study.load_checkpoint(path)
    assert study._snapshot() == before
