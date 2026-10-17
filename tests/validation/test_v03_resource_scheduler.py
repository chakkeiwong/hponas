"""Resource admission cannot change test attribution or the mutant population."""
import copy
import hashlib
import json
from math import ceil
from types import SimpleNamespace

import pytest

from validation.v03_resource_scheduler import (
    Admission, POLICY_PATH, make_rows, policy, sha256, verify_schedule, verify_trace,
)

CFG = SimpleNamespace(timeout_constant=22.0, timeout_multiplier=3.0)


def fixture():
    high = 'tests/integration/test_ray_streaming.py::test_runtime'
    selections = {'hponas.space.x_f': [high, 'tests/a.py::a'],
                  'hponas.events.x_g': ['tests/b.py::b'], 'hponas.store.x_h': []}
    durations = {high: 12.1, 'tests/a.py::a': .2, 'tests/b.py::b': 2.0}
    names = [f'{function}__mutmut_{i}' for function in selections for i in range(1, 11)]
    mutants = [(None, name, None) for name in names]
    return mutants, selections, durations


def test_population_tests_timeouts_and_classification_are_outcome_blind():
    mutants, selections, durations = fixture()
    rows = make_rows(mutants, selections, durations, CFG)
    changed = [(None, name, i % 4) for i, (_, name, _) in enumerate(reversed(mutants))]
    assert rows == make_rows(changed, selections, durations, CFG)
    assert {row['mutant'] for row in rows} == {name for _, name, _ in mutants}
    assert len(rows) == len(mutants)
    for row in rows:
        assert row['tests'] == sorted(selections[row['function']])
        expected = sum(durations[test] for test in row['tests'])
        assert row['cpu_time_limit_seconds'] == ceil((expected + 22) * 3 * 2)
    assert {row['resource_class'] for row in rows if row['function'] == 'hponas.space.x_f'} == {'high_memory'}


@pytest.mark.parametrize('damage', ['population', 'test', 'timeout', 'class', 'policy', 'stats'])
def test_frozen_manifest_is_reconstructed_not_trusted(damage):
    mutants, selections, durations = fixture()
    rows = make_rows(mutants, selections, durations, CFG)
    stats = {'tests_by_mangled_function_name': selections, 'duration_by_test': durations}
    schedule = {'kind': 'v03_complete_resource_schedule_v1', 'rows': copy.deepcopy(rows),
                'policy_sha256': sha256(POLICY_PATH),
                'stats_sha256': hashlib.sha256(json.dumps(stats, sort_keys=True).encode()).hexdigest()}
    listing = {'mutants': [{'id': name} for _, name, _ in mutants]}
    assert verify_schedule(schedule, stats, listing, CFG) == rows
    if damage == 'population': schedule['rows'].pop()
    elif damage == 'test': schedule['rows'][0]['tests'].clear()
    elif damage == 'timeout': schedule['rows'][0]['cpu_time_limit_seconds'] += 1
    elif damage == 'class': schedule['rows'][0]['reserved_gib'] = 0
    elif damage == 'policy': schedule['policy_sha256'] = 'unfrozen'
    else: schedule['stats_sha256'] = 'unfrozen'
    with pytest.raises(ValueError, match='differs'):
        verify_schedule(schedule, stats, listing, CFG)


def test_admission_preserves_memory_and_cpu_slots_and_reclaims_abnormal_completion():
    rows = make_rows(*fixture(), CFG)
    high = [row for row in rows if row['resource_class'] == 'high_memory']
    regular = [row for row in rows if row['resource_class'] == 'regular' and row['tests']]
    admission = Admission()
    for row in high[:8]: admission.submit(row)
    assert not admission.can_submit(high[8])
    assert not admission.can_submit(regular[0])
    # Reaping reclaims the same reservation irrespective of a raw return code.
    admission.complete(high[0]['mutant'])
    admission.submit(regular[0])
    assert sum(row['reserved_gib'] for row in admission.pending.values()) <= 52
    with pytest.raises(ValueError): admission.submit(high[8])
    with pytest.raises(ValueError): admission.complete('never_submitted')


@pytest.mark.parametrize('damage', [None, 'raw_code', 'drop', 'repeat', 'priority', 'overbook'])
def test_trace_replay_preserves_raw_outcomes_and_rejects_missing_or_excess_jobs(damage):
    rows = [row for row in make_rows(*fixture(), CFG) if row['tests']]
    queued = sorted(rows, key=lambda row: (-row['estimated_test_seconds'], row['mutant']))
    admission, trace, raw = Admission(), [], {}
    while queued or admission.pending:
        candidate = next((row for row in queued if admission.can_submit(row)), None)
        if candidate:
            admission.submit(candidate); queued.remove(candidate)
            trace.append({'kind': 'submit', 'mutant': candidate['mutant']})
        else:
            name = next(iter(admission.pending)); admission.complete(name)
            raw[name] = [0, 1, -24, -11][len(raw) % 4]
            trace.append({'kind': 'complete', 'mutant': name, 'exit_code': raw[name]})
    verify_trace(trace, rows, raw)
    if damage is None: return
    if damage == 'raw_code': raw[next(iter(raw))] = 255
    elif damage == 'drop': trace.pop()
    elif damage == 'repeat': trace.append(trace[0])
    elif damage == 'priority': trace[0], trace[1] = trace[1], trace[0]
    else:
        ninth = next(i for i, row in enumerate(trace) if i > 7 and row['kind'] == 'submit')
        trace.insert(8, trace.pop(ninth))
    with pytest.raises(ValueError): verify_trace(trace, rows, raw)


def test_duplicate_population_and_invalid_clean_measurement_are_refused():
    mutants, selections, durations = fixture()
    with pytest.raises(ValueError, match='Duplicate'):
        make_rows(mutants + mutants[:1], selections, durations, CFG)
    durations['tests/b.py::b'] = float('nan')
    with pytest.raises(ValueError, match='duration'):
        make_rows(mutants, selections, durations, CFG)
