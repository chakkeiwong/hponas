"""General adapters: independent arithmetic, inherited schedules and crash barriers."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math

import pytest

from hponas.evaluation import StudyDeclaration, EvaluationFold, EvaluationObjective, EvaluationContext
from hponas.population_adapter import AdapterPopulation, _digest
from examples.population_adapters import LinearSGDAdapter, LogisticAdamAdapter


def declaration():
    return StudyDeclaration('loss', 'caller-model', 'tiny-data', 'population-test-v1',
        (EvaluationObjective('loss', 'min', 'loss'),),
        (EvaluationFold('tune', ('x1', 'x2'), ('v1', 'v2')),),
        (EvaluationFold('final', ('x1', 'x2'), ('z1', 'z2')),))


def linear(lr, momentum=0.):
    return dict(model='linear', lr=lr, momentum=momentum)


def adam(lr, beta1=.9):
    return dict(model='logistic', lr=lr, beta1=beta1, beta2=.99)


def linear_data():
    return {k: (x, 2*x) for k, x in [('x1', 1.), ('x2', 2.), ('v1', 1.),
                                    ('v2', 2.), ('z1', 3.), ('z2', 4.)]}


def engine(tmp_path, adapter=None, **changes):
    options = dict(exploration_configs=[linear(.2)], max_updates=12)
    options.update(changes)
    return AdapterPopulation(tmp_path/'population.json', adapter or LinearSGDAdapter(linear_data()),
        declaration(), {'a': linear(.05), 'b': linear(.1)}, **options)


def test_closed_form_momentum_and_actual_adam_first_step():
    d = declaration()
    context = EvaluationContext('tuning', d.tuning_folds[0], d.identity)
    adapter = LinearSGDAdapter(linear_data())
    cfg = linear(.1, .5)
    runtime = adapter.initialize(cfg, seed=0, evaluation=context)
    adapter.train(runtime, cfg, evaluation=context)
    assert runtime == dict(model='linear-sgd-v1', w=1., velocity=-10., updates=1)
    adapter.train(runtime, cfg, evaluation=context)
    assert runtime['w'] == 2. and runtime['velocity'] == -10.

    logistic = LogisticAdamAdapter({'x1': (0., 0), 'x2': (1., 1)})
    cfg = adam(.1)
    state = logistic.initialize(cfg, seed=1, evaluation=context)
    logistic.train(state, cfg, evaluation=context)
    # At zero logits, gradient = (-1/4, 0). Bias correction cancels
    # (1-beta) on the first step; calculate without the adapter's helpers.
    assert state['w'] == pytest.approx([.1 * .25 / (.25 + 1e-8), 0.], abs=1e-14)
    assert state['m'] == pytest.approx([-.025, 0.])
    assert state['v'] == pytest.approx([.000625, 0.])


def test_full_repetitions_inherited_schedule_and_frozen_final(tmp_path):
    result = engine(tmp_path).run()
    assert result['status'] == 'complete'
    assert result['selection']['member'] == 'a'
    schedule = result['selection']['schedule']
    assert [row['config']['lr'] for row in schedule] == [.1, .2]
    assert [row['optimizer_policy'] for row in schedule] == ['INITIAL', 'COPY']
    assert result['final_mean'] == pytest.approx(0., abs=1e-14)
    assert len(result['final_records']) == 2
    assert result['accounting']['lower'] == result['accounting']['upper'] == 12
    events = result['events']
    freeze = next(i for i, e in enumerate(events) if e['key'] == 'freeze')
    assert all(e['request']['role'] == 'tuning' for e in events[:freeze+1])
    assert all(e['request']['role'] == 'final' for e in events[freeze+1:])
    assert len(result['lineage']) == 2
    assert all(e['request']['parent'] == 'b' and e['request']['member'] == 'a' for e in result['lineage'])
    # Identical names/seed/fold identities restore without any training dispatch.
    again = engine(tmp_path)
    again.adapter.train = lambda *a, **kw: pytest.fail('Committed work was repeated')
    again.adapter.evaluate = lambda *a, **kw: pytest.fail('Committed evaluation was repeated')
    assert again.run() == result


@pytest.mark.parametrize('policy', ['COPY', 'RESET'])
def test_final_replays_optimizer_policy_by_independent_recurrence(tmp_path, policy):
    adapter = LinearSGDAdapter(linear_data())
    d = declaration()
    run = AdapterPopulation(tmp_path/'p.json', adapter, d,
        {'a': linear(.02, .5), 'b': linear(.07, .5)},
        exploration_configs=[linear(.1, .5)], optimizer_policy=policy, max_updates=18,
        rounds=3).run()
    assert run['status'] == 'complete'
    w = velocity = 0.
    for row in run['selection']['schedule']:
        if row['optimizer_policy'] == 'RESET':
            velocity = 0.
        for _ in range(row['updates']):
            velocity = row['config']['momentum'] * velocity + 5 * (w - 2)
            w -= row['config']['lr'] * velocity
    expected = ((3*w-6)**2 + (4*w-8)**2)/2
    assert run['final_mean'] == pytest.approx(expected, abs=1e-13)


def test_logistic_adam_complete_distinct_model_optimizer(tmp_path):
    data = {k: (x, y) for k, x, y in [('x1',0.,0),('x2',1.,1),('v1',0.,0),
                                     ('v2',2.,1),('z1',-1.,0),('z2',3.,1)]}
    adapter = LogisticAdamAdapter(data)
    result = AdapterPopulation(tmp_path/'adam.json', adapter, declaration(),
        {'slow': adam(.01), 'fast': adam(.1)}, exploration_configs=[adam(.2)],
        optimizer_policy='RESET', max_updates=12).run()
    assert result['status'] == 'complete'
    assert result['accounting']['work_unit'] == 'logistic_adam_gradient_update'
    assert math.isfinite(result['final_mean']) and result['final_mean'] < math.log(2)
    assert result['lineage'][0]['result']['model'] == 'logistic-adam-v1'


def test_seeded_exploration_uses_stable_hash_index(tmp_path):
    roster = [linear(.03), linear(.06), linear(.09)]
    result = AdapterPopulation(tmp_path/'stable.json', LinearSGDAdapter(linear_data()),
        declaration(), {'a': linear(.02), 'b': linear(.04)},
        exploration_configs=roster, rounds=2, seed=19, max_updates=12).run()
    expected_index = int.from_bytes(hashlib.sha256(b'19:0').digest()[:8], 'big') % len(roster)
    transfer = next(e for e in result['lineage'] if e['request']['role'] == 'tuning')
    assert transfer['request']['config'] == roster[expected_index]


def test_incompatible_transfer_refused_and_adam_decay_requires_reset():
    context = EvaluationContext('tuning', declaration().tuning_folds[0], declaration().identity)
    a = LinearSGDAdapter(linear_data())
    checkpoint = a.initialize(linear(.1), seed=0, evaluation=context)
    with pytest.raises(ValueError, match='Incompatible'):
        a.transfer(checkpoint, linear(.1), adam(.1), optimizer_policy='COPY', seed=0, evaluation=context)
    b = LogisticAdamAdapter({'x1': (0.,0), 'x2': (1.,1)})
    cp = b.initialize(adam(.1), seed=0, evaluation=context)
    with pytest.raises(ValueError, match='decay'):
        b.transfer(cp, adam(.1), adam(.1,.8), optimizer_policy='COPY', seed=0, evaluation=context)
    assert b.transfer(cp, adam(.1), adam(.1,.8), optimizer_policy='RESET', seed=0, evaluation=context)['t'] == 0


@pytest.mark.parametrize('failure', ['exception', 'nan', 'lost'])
def test_failed_repetition_has_no_selection_or_partial_checkpoint_donation(tmp_path, failure):
    a = LinearSGDAdapter(linear_data())
    original = a.train
    calls = []

    def train(runtime, config, *, evaluation):
        original(runtime, config, evaluation=evaluation)
        calls.append(evaluation.role)
        if failure == 'lost':
            raise KeyboardInterrupt('simulated host loss before commit')
        if failure == 'exception':
            raise RuntimeError('after actual work')
        runtime['w'] = float('nan')

    a.train = train
    runner = engine(tmp_path, a)
    if failure == 'lost':
        with pytest.raises(KeyboardInterrupt):
            runner.run()
        runner = engine(tmp_path)
    result = runner.run()
    assert result['status'] == 'failed'
    assert result['selection'] is None and result['final_mean'] is None
    assert result['accounting']['lower'] == 0 and result['accounting']['upper'] == 1
    assert len(calls) == 1 and result['events'][-1]['result'] is None
    assert not result['lineage']


def test_final_failure_cannot_change_frozen_selection(tmp_path):
    a = LinearSGDAdapter(linear_data())
    evaluate = a.evaluate
    def score(runtime, *, evaluation):
        if evaluation.role == 'final':
            raise RuntimeError('final scoring unavailable')
        return evaluate(runtime, evaluation=evaluation)
    a.evaluate = score
    result = engine(tmp_path, a).run()
    assert result['status'] == 'failed' and result['selection']['member'] == 'a'
    assert result['final_mean'] is None
    assert result['accounting']['calls']['evaluate']['uncertain'] == 1


def test_acknowledged_prefix_recovers_after_crash(tmp_path, monkeypatch):
    a = engine(tmp_path)
    write = a._write
    def crash_after_commit(state):
        write(state)
        if state['events'] and state['events'][-1]['key'] == 'train:0:a:0:0' and state['events'][-1]['status'] == 'committed':
            raise KeyboardInterrupt('host loss after durable commit')
    monkeypatch.setattr(a, '_write', crash_after_commit)
    with pytest.raises(KeyboardInterrupt):
        a.run()
    restored = engine(tmp_path).run()
    assert restored['status'] == 'complete' and restored['accounting']['upper'] == 12
    assert sum(e['key'] == 'train:0:a:0:0' for e in restored['events']) == 1


def test_seal_commit_recovers_without_repeating_any_adapter_call(tmp_path, monkeypatch):
    a = engine(tmp_path)
    write = a._write
    def crash_after_seal(state):
        write(state)
        if state['events'] and state['events'][-1]['key'] == 'seal' and state['events'][-1]['status'] == 'committed':
            raise KeyboardInterrupt('host loss after durable score seal')
    monkeypatch.setattr(a, '_write', crash_after_seal)
    with pytest.raises(KeyboardInterrupt):
        a.run()
    restored = engine(tmp_path)
    restored.adapter.train = lambda *a, **kw: pytest.fail('Committed training repeated')
    restored.adapter.evaluate = lambda *a, **kw: pytest.fail('Committed scoring repeated')
    result = restored.run()
    assert result['status'] == 'complete' and len(result['final_records']) == 2
    assert result['accounting']['calls']['evaluate']['uncertain'] == 0


@pytest.mark.parametrize('damage', ['checksum', 'lineage', 'selection', 'order', 'trailing', 'checkpoint', 'final_score'])
def test_corruption_refuses_even_if_envelope_is_rehashed(tmp_path, damage):
    a = engine(tmp_path)
    a.run()
    envelope = json.loads(a.path.read_text())
    events = envelope['payload']['events']
    if damage == 'checksum':
        envelope['sha256'] = '0'*64
    elif damage == 'lineage':
        next(e for e in events if e['request']['operation'] == 'transfer')['request']['parent'] = 'a'
    elif damage == 'selection':
        e = next(e for e in events if e['key'] == 'freeze')
        e['result']['member'] = 'b'
        e['result_sha256'] = _digest(e['result'])
    elif damage == 'order':
        events[0], events[1] = events[1], events[0]
    elif damage == 'trailing':
        e = deepcopy(events[-1]); e['key'] = 'unexpected'; events.append(e)
    elif damage == 'final_score':
        e = next(e for e in reversed(events) if e['key'].startswith('final:score:'))
        e['result'] = 999.0
        e['result_sha256'] = _digest(e['result'])
    else:
        e = events[0]; e['result']['w'] = 99.; e['result_sha256'] = _digest(e['result'])
    if damage != 'checksum':
        envelope['sha256'] = _digest(envelope['payload'])
    a.path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError):
        engine(tmp_path).run()


def test_public_package_exports_adapter_population():
    from hponas import AdapterPopulation, PopulationExecutionError, PopulationAdapter
    from hponas.population_adapter import AdapterPopulation as ModulePopulation
    assert AdapterPopulation is ModulePopulation
    assert issubclass(PopulationExecutionError, RuntimeError)
    assert PopulationAdapter.__module__ == 'hponas.population_adapter'


@pytest.mark.parametrize('change', [dict(max_updates=11), dict(rounds=True), dict(optimizer_policy='AUTO')])
def test_reservations_refuse_before_any_checkpoint_is_created(tmp_path, change):
    with pytest.raises(ValueError):
        engine(tmp_path, **change)
    assert not (tmp_path/'population.json').exists()


def test_changed_contract_and_vector_declaration_refuse(tmp_path):
    engine(tmp_path)
    with pytest.raises(ValueError, match='contract'):
        engine(tmp_path, seed=1)
    d = replace(declaration(), objectives=(EvaluationObjective('loss','min','loss'),
                                          EvaluationObjective('work','min','updates')))
    with pytest.raises(ValueError, match='scalar'):
        AdapterPopulation(tmp_path/'v.json', LinearSGDAdapter(linear_data()), d,
                          {'a':linear(.1),'b':linear(.2)}, exploration_configs=[linear(.1)], max_updates=12)
