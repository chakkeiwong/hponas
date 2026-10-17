"""Adverse finite DEHB evidence checks against independent spectral dynamics."""
from copy import deepcopy
from pathlib import Path
import pytest

from validation.dehb_finite import execute_slot, verify_raw
from validation.evidence import decision


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    slot = {'id': 'neutral-7', 'initial': [2., 3.], 'seed': 7}
    raw = execute_slot(slot, tmp_path_factory.mktemp('dehb') / 'case')
    return slot, raw


def test_native_gradient_updates_recover_and_match_spectral_powers(retained):
    slot, raw = retained
    report = verify_raw(slot, raw)
    assert 50 <= report['gradient_updates'] <= 400
    assert report['regret'] >= -2e-12


@pytest.mark.parametrize('bad', ['state', 'loss', 'coordinate', 'work', 'selection', 'recovery', 'missing', 'nonfinite'])
def test_forged_or_incomplete_raw_evidence_cannot_pass(retained, bad):
    slot, original = retained
    raw = deepcopy(original)
    row = raw['trace'][0]
    if bad == 'state': row['updates'][0]['state'][0] += .1
    elif bad == 'loss': row['updates'][0]['loss'] += .1
    elif bad == 'coordinate': row['job']['values']['x'] += .1
    elif bad == 'work': raw['gradient_updates'] -= 1
    elif bad == 'selection': raw['best'] = None
    elif bad == 'recovery': raw['recoveries'][0]['state']['history'].pop()
    elif bad == 'missing': raw['trace'].pop()
    else: row['updates'][0]['loss'] = float('nan')
    with pytest.raises(ValueError): verify_raw(slot, raw)


def test_supplied_pass_does_not_replace_a_frozen_trace():
    assert decision('V07', {'passed': True, 'verdict': 'PASS'}) == 'INCONCLUSIVE'


def test_public_validator_requires_immutable_evidence():
    from validation.validators.v07_validator import V07Validator
    assert not V07Validator().audit().passed


def test_registered_task_refuses_legacy_design_before_creating_work(tmp_path):
    from validation.task_registry import get_validation_task
    with pytest.raises(ValueError, match='retired'):
        get_validation_task('V07').protocol(artifact_root=tmp_path, smoke=True)
    assert not list(tmp_path.iterdir())


def test_protocol_disclosure_preflight_detects_the_retained_audit_failure(tmp_path):
    from validation.evidence import ROOT
    from validation.v16_audit_enforcer import V16Enforcer
    current = ROOT / 'validation/protocols/v07_protocol.md'
    original = tmp_path / 'v07_protocol.md'
    original.write_text(current.read_text().replace('## Known Issues', ''))
    assert not V16Enforcer(original)._check_known_issues_disclosure(tmp_path).passed
    assert V16Enforcer(current)._check_known_issues_disclosure(tmp_path).passed


def test_registered_dispatch_uses_native_dehb_and_preserves_audit(tmp_path, monkeypatch):
    import validation.dehb_finite as finite
    from validation.task_registry import get_validation_task
    calls = []
    monkeypatch.setattr(finite, 'require_phase', lambda: {'run_path': str(tmp_path / 'V07/dispatch')})
    def probe(directory):
        calls.append(Path(directory))
        return {'schema_version': 1, 'validation_id': 'V07', 'blocked_reason': 'dispatch test'}
    monkeypatch.setattr(finite, 'campaign', probe)
    result = get_validation_task('V07').protocol(artifact_root=tmp_path)
    assert calls == [tmp_path / 'V07/dispatch']
    assert result['verdict'] == 'INCONCLUSIVE'
    import json
    assert json.loads((calls[0] / 'v16_audit.json').read_text())['passed']


def test_interruption_retains_work_consumes_slots_and_never_retries(tmp_path, monkeypatch):
    import validation.dehb_finite as finite
    monkeypatch.setattr(finite, 'require_phase', lambda: {'run_path': str(tmp_path)})
    calls = []
    def interrupted(slot, directory):
        calls.append(slot['id'])
        directory.mkdir()
        (directory / 'partial.txt').write_text('work was attempted')
        raise RuntimeError('deliberate interruption')
    monkeypatch.setattr(finite, 'execute_slot', interrupted)
    result = finite.campaign(tmp_path)
    assert len(calls) == 1 and result['generation_complete'] is False
    for _ in range(3):
        assert finite.reconstruct(result)['verdict'] == 'INCONCLUSIVE'
    with pytest.raises(ValueError, match='exhausted'):
        finite.reconstruct(result)
    with pytest.raises(FileExistsError):
        finite.campaign(tmp_path)
    assert len(calls) == 1 and (tmp_path / 'slot-00/partial.txt').is_file()
