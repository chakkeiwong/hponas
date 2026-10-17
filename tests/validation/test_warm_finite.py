"""Independent finite warm-start reconstruction and adverse evidence controls."""
from copy import deepcopy

import pytest

from validation.warm_finite_contract import contract
from validation.warm_finite_producer import execute_slot
from validation.warm_finite_reference import verify_raw


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp('warm-finite')/'case'
    slot = {**contract()['slots'][0], 'id':'neutral', 'history_curvature':1.5, 'target_curvature':2.5}
    return slot, execute_slot(slot, directory), directory


def test_real_histories_and_target_training_match_independent_references(retained):
    slot, raw, directory = retained
    result = verify_raw(slot, raw, directory)
    assert result['gradient_updates'] == 144
    assert result['selected_seeds'] == 3
    assert len(result['excluded']) == 3
    assert result['empirical_speedup_established'] is False


@pytest.mark.parametrize('defect', ['state','work','value','selection','history','cutoff','pending','prefix','missing','contamination','seed'])
def test_forged_missing_or_leaking_evidence_is_rejected(retained, defect):
    slot, source, _ = retained
    raw = deepcopy(source)
    if defect == 'state': raw['studies'][6]['updates'][0]['state'] += .2
    elif defect == 'work': raw['physical_updates'] -= 1
    elif defect == 'value': raw['studies'][6]['result']['history'][0]['objective_value'] += .2
    elif defect == 'selection': raw['selection']['seeds'].reverse()
    elif defect == 'history': raw['histories'][0]['trials'][0]['value'] += 1
    elif defect == 'cutoff': raw['context']['history_cutoff'] += 1000
    elif defect == 'pending': raw['studies'][6]['recovery']['after']['pending'] = []
    elif defect == 'prefix': raw['studies'][6]['recovery']['before']['results']['target_trial_0']['cost'] = 0
    elif defect == 'missing': raw['studies'].pop()
    elif defect == 'contamination': raw['initial_warm']['base']['history'] = [{'trial_id':'A_trial_0'}]
    else: raw['studies'][7]['seed'] += 1
    with pytest.raises(ValueError):
        verify_raw(slot, raw)


@pytest.mark.parametrize('name', ['cold','ties','maximize','scale','shifted'])
def test_declared_edge_cases_conform(tmp_path, name):
    slot = next(r for r in contract()['slots'] if r['id'] == name)
    result = verify_raw(slot, execute_slot(slot, tmp_path/name), tmp_path/name)
    assert result['selected_seeds'] == (0 if name == 'cold' else 3)


def test_retained_physical_log_is_required(retained):
    slot, source, directory = retained
    path = directory/'physical-updates.jsonl'
    original = path.read_bytes()
    try:
        path.write_bytes(original.split(b'\n',1)[1])
        with pytest.raises(ValueError,match='physical record'):
            verify_raw(slot, source, directory)
    finally:
        path.write_bytes(original)


def test_supplied_pass_cannot_replace_raw_evidence():
    from validation.evidence import decision
    from validation.validators.v12_validator import V12Validator
    assert decision('V12', {'passed':True, 'verdict':'PASS'}) == 'INCONCLUSIVE'
    assert not V12Validator().audit().passed


def test_protocol_check_rejects_changed_contract_and_default_claim():
    import json
    from validation.evidence import ROOT
    from tools.check_protocols import check_finite_warm
    registry=json.loads((ROOT/'validation/protocols.json').read_text())
    assert check_finite_warm(registry) == []
    changed=deepcopy(registry)
    changed['entries']['V12']['contract']['target_trials'] += 1
    assert check_finite_warm(changed)
    changed=deepcopy(registry)
    changed['policy']['finite_warm']['default_activation']=True
    assert check_finite_warm(changed)


def test_dispatch_uses_warm_producer_and_refuses_legacy_modes(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    import validation.warm_finite_campaign as finite
    from validation.task_registry import get_validation_task
    task = get_validation_task('V12')
    with pytest.raises(ValueError,match='retired'):
        task.protocol(artifact_root=tmp_path, smoke=True)
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(finite,'require_phase',lambda: {'run_path':str(tmp_path/'V12/dispatch')})
    calls=[]
    def probe(directory):
        calls.append(Path(directory))
        return {'schema_version':1,'validation_id':'V12','blocked_reason':'dispatch test'}
    monkeypatch.setattr(finite,'campaign',probe)
    result = task.protocol(artifact_root=tmp_path)
    assert calls == [tmp_path/'V12/dispatch']
    assert result['verdict'] == 'INCONCLUSIVE'
    assert json.loads((calls[0]/'v16_audit.json').read_text())['passed']


def test_interrupted_generation_is_never_retried_and_reconstruction_is_bounded(tmp_path,monkeypatch):
    import validation.warm_finite_campaign as finite
    monkeypatch.setattr(finite,'require_phase',lambda: {'run_path':str(tmp_path)})
    calls=[]
    def interrupted(slot,directory):
        calls.append(slot['id'])
        directory.mkdir()
        (directory/'physical-updates.jsonl').write_text('{"partial_work":true}\n')
        raise RuntimeError('interrupted after work')
    monkeypatch.setattr(finite,'execute_slot',interrupted)
    result=finite.campaign(tmp_path)
    assert result['generation_complete'] is False and len(calls) == 1
    for _ in range(3):
        assert finite.reconstruct(result)['verdict'] == 'INCONCLUSIVE'
    with pytest.raises(ValueError,match='exhausted'):
        finite.reconstruct(result)
    with pytest.raises(FileExistsError):
        finite.campaign(tmp_path)
    assert len(calls) == 1 and (tmp_path/'slot-00/physical-updates.jsonl').is_file()
