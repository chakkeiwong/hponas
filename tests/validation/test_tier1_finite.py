"""Finite Tier-1 preparation: physical models, adverse evidence and identities."""
from copy import deepcopy
import pytest

from validation.tier1_contract import ENTRIES, contract, slots
from validation.tier1_producers import execute_slot
from validation.tier1_reference import verify_slot
from validation.tier1_campaign import replay_slot, projection


CASES = [(entry,slot) for entry in ENTRIES for slot in slots(entry)]


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    root=tmp_path_factory.mktemp('tier1-development')
    return {(entry,spec['id']):(spec,execute_slot(spec,root/f'{entry}-{spec["id"]}')) for entry,spec in CASES}


def test_fixed_nonempty_unique_rosters_and_no_default_claim():
    assert [len(slots(entry)) for entry in ENTRIES]==[7,14,4,2,6,8,6,24]
    for entry in ENTRIES:
        assert len({s['id'] for s in slots(entry)})==len(slots(entry))
        assert contract(entry)['release']=='finite_opt_in_capability_only_no_default_or_population_inference'
    with pytest.raises(ValueError):
        slots('V11')


@pytest.mark.parametrize('key',[(entry,spec['id']) for entry,spec in CASES])
def test_physical_reference_and_actual_method_identity(retained,key):
    spec,raw=retained[key]
    assert verify_slot(spec,raw).get('status')!='INCONCLUSIVE'
    assert replay_slot(spec,raw)=='PASS'


@pytest.mark.parametrize('key',[('V04-T1','integer'),('V11a','categorical'),('V11b','integer-log')])
def test_changed_physical_update_is_rejected(retained,key):
    spec,raw=deepcopy(retained[key])
    raw['updates'][0]['value']+=.01
    with pytest.raises(ValueError):
        verify_slot(spec,raw)


def test_pibo_inverted_or_omitted_log_weight_is_rejected(retained):
    spec,raw=deepcopy(retained[('V11a','pibo')])
    raw['probes'][0]['weighted']=raw['probes'][0]['base']
    with pytest.raises(ValueError):
        verify_slot(spec,raw)


def test_vector_fake_front_or_work_is_rejected(retained):
    spec,raw=deepcopy(retained[('V09','random')])
    raw['observations']['metrics']['hypervolume']+=.01
    with pytest.raises(ValueError):
        verify_slot(spec,raw)


def test_promoted_absolute_veto_is_rejected(retained):
    spec,raw=deepcopy(retained[('V10','advisory-reversal')])
    raw['events'][4]['promotions'].append(['C',2])
    with pytest.raises(ValueError):
        verify_slot(spec,raw)


def test_hmc_fake_transition_and_veto_are_rejected(retained):
    spec,raw=deepcopy(retained[('V13','stable')])
    raw['result']['checkpoint']['trace'][0]['transitions'][0]['next_q']+=.01
    with pytest.raises(ValueError):
        verify_slot(spec,raw)
    spec,raw=deepcopy(retained[('V13','stable')])
    raw['result']['veto']['eligible_for_calibration']=True
    with pytest.raises(ValueError):
        verify_slot(spec,raw)


def test_wrong_method_label_cannot_reuse_valid_objectives(retained):
    spec,raw=deepcopy(retained[('V09','random')])
    raw['observations']['method']='nsgaii'
    with pytest.raises(ValueError):
        verify_slot(spec,raw)


def test_projection_does_not_hide_physical_work(retained):
    spec,raw=deepcopy(retained[('V09','random')])
    before=projection(spec,raw)
    raw['observations']['history'][0]['metadata']['multi_objective']['work']+=1
    assert projection(spec,raw)!=before


def test_serialized_state_replays_with_integer_keys(retained):
    import json
    spec,raw=retained[('V10','advisory-reversal')]
    assert replay_slot(spec,json.loads(json.dumps(raw)))=='PASS'


def test_vector_resource_timing_is_descriptive_but_retained_and_validated(retained):
    from validation.tier1_campaign import validate_timings
    spec, raw = retained[('V09', 'random')]
    original = deepcopy(raw)
    changed = deepcopy(raw)
    seconds = raw['observations']['resources']['tuning_elapsed_seconds']
    changed['observations']['resources']['tuning_elapsed_seconds'] = seconds + 1.0
    validate_timings(raw)
    validate_timings(changed)
    assert projection(spec, raw) == projection(spec, changed)
    assert raw == original
    assert changed['observations']['resources']['tuning_elapsed_seconds'] == seconds + 1.0


@pytest.mark.parametrize('value', [-1., float('inf'), float('nan'), True, '1', None])
def test_invalid_resource_timing_cannot_be_hidden_by_projection(value):
    from validation.tier1_campaign import validate_timings
    with pytest.raises(ValueError, match='Nonfinite or negative measured timing'):
        validate_timings({'observations': {'resources': {'tuning_elapsed_seconds': value}}})


@pytest.mark.parametrize('field', ['configurations_proposed', 'tuning_evaluations',
                                  'configuration_limit', 'tuning_seconds_limit'])
def test_vector_resource_counts_and_limits_remain_in_replay(retained, field):
    spec, raw = retained[('V09', 'random')]
    changed = deepcopy(raw)
    before = changed['observations']['resources'][field]
    changed['observations']['resources'][field] = 1 if before is None else before + 1
    assert projection(spec, raw) != projection(spec, changed)
