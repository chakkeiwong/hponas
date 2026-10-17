"""Finite V08 source guards, once-only allocation and adverse raw receipts."""
from copy import deepcopy
import json

import pytest

from validation import population_campaign as campaign
from validation.evidence import decision
from validation.run_validation_with_audit import ValidationRunner


@pytest.fixture
def development_phase(tmp_path, monkeypatch):
    # No production bypass: only this temporary test-local phase is substituted.
    run = tmp_path/'V08'/'development'
    phase = {'test_only': True, 'run_path': str(run)}
    monkeypatch.setattr(campaign, 'require_phase', lambda: phase)
    return run


def test_runner_recomputes_raw_result_and_v16_with_strict_reconstruction_allocation(development_phase):
    runner = ValidationRunner('V08', artifact_root=development_phase.parent.parent)
    assert runner.run(lambda: campaign.campaign(runner.run_dir))
    result = json.loads((runner.run_dir/'results.json').read_text())
    assert result['verdict'] == 'PASS'
    assert json.loads((runner.run_dir/'v16_audit.json').read_text())['passed']
    result['verdict'], result['passed'] = 'FAIL', False
    assert decision('V08', result) == 'PASS'  # Supplied labels are not evidence.
    with pytest.raises(ValueError, match='exhausted'):
        decision('V08', result)
    with pytest.raises(FileExistsError):
        campaign.campaign(runner.run_dir)
    assert len(list(runner.run_dir.glob('reconstruction-*-start.json'))) == 3
    assert len(list(runner.run_dir.glob('reconstruction-*-result.json'))) == 3


def test_unfrozen_phase_and_wrong_location_refuse_before_creating_evidence(tmp_path, monkeypatch):
    directory = tmp_path/'docs/program'
    directory.mkdir(parents=True)
    (directory/'program.json').write_text(json.dumps({'decisions': [], 'continuation': {'steps': []}}))
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='not frozen'):
        ValidationRunner('V08', artifact_root=tmp_path/'uncreated')
    assert not (tmp_path/'uncreated').exists()
    monkeypatch.setattr(campaign, 'require_phase', lambda: {'run_path': str(tmp_path/'allocated')})
    with pytest.raises(ValueError, match='once-only'):
        campaign.campaign(tmp_path/'replacement')
    assert not (tmp_path/'replacement').exists()


@pytest.fixture(scope='module')
def raw_development_campaign(tmp_path_factory):
    directory = tmp_path_factory.mktemp('v08-adverse')
    phase = {'test_only': True, 'run_path': str(directory)}
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(campaign, 'require_phase', lambda: phase)
        result = campaign.campaign(directory)
    return directory, phase, result


@pytest.mark.parametrize('fault', ['source', 'runtime', 'raw', 'roster', 'physical_checkpoint'])
def test_campaign_rejects_mutated_bound_evidence(raw_development_campaign, monkeypatch, fault):
    directory, phase, original = raw_development_campaign
    result = deepcopy(original)
    monkeypatch.setattr(campaign, 'require_phase', lambda: phase)
    changed = None
    if fault == 'source':
        monkeypatch.setattr(campaign, 'source_digest', lambda: 'wrong')
    elif fault == 'runtime':
        monkeypatch.setattr(campaign, 'require_runtime', lambda: {'wrong': True})
    elif fault == 'roster':
        path = directory/'slots.json'
        before = path.read_bytes()
        path.write_text(json.dumps(json.loads(before)[:-1]))
        result['slots'] = campaign.binding(path)
        changed = path, before
    else:
        path = directory/('raw-000.json' if fault == 'raw' else 'slot-003/population.json')
        changed = path, path.read_bytes()
        path.write_text('{}')
    try:
        with pytest.raises((ValueError, KeyError)):
            campaign._reconstruct(result, directory)
    finally:
        if changed:
            changed[0].write_bytes(changed[1])


def test_interrupted_allocation_start_cannot_be_silently_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'require_runtime', lambda: {'development': True})
    assert campaign.consume_reconstruction(tmp_path) == 1
    assert campaign.consume_reconstruction(tmp_path) == 2
    assert campaign.consume_reconstruction(tmp_path) == 3
    with pytest.raises(ValueError, match='exhausted'):
        campaign.consume_reconstruction(tmp_path)


def test_failed_slot_preserves_partial_work_without_replacement(development_phase, monkeypatch):
    run = development_phase
    calls = []
    real = campaign.execute_slot
    def fail(spec, directory):
        calls.append(spec['id'])
        if spec['kind'] == 'generations':
            directory.mkdir()
            (directory/'partial.json').write_text('{"unknown_work": true}')
            raise RuntimeError('deliberate incomplete slot')
        return real(spec, directory)
    monkeypatch.setattr(campaign, 'execute_slot', fail)
    run.mkdir(parents=True)
    result = campaign.campaign(run)
    assert campaign.reconstruct(result)['verdict'] == 'INCONCLUSIVE'
    assert calls.count('bg-generations') == 1
    assert (run/'slot-009/partial.json').is_file()


def test_old_v08_pass_labels_do_not_satisfy_finite_claim():
    assert decision('V08', {'schema_version': 1, 'validation_id': 'V08', 'verdict': 'PASS', 'passed': True}) == 'INCONCLUSIVE'


def test_registry_scope_and_legacy_validator_cannot_drift():
    from tools.check_protocols import check_finite_population
    from validation.validators.v08_validator import V08Validator
    registry = json.loads((campaign.ROOT/'validation/protocols.json').read_text())
    assert not check_finite_population(registry)
    registry['entries']['V08']['power_target'] = 0.9
    assert check_finite_population(registry)
    assert not V08Validator().audit().passed


def test_frozen_phase_checks_exact_source_runtime_rules_and_allocation(tmp_path, monkeypatch):
    from tools.program_state import canonical_digest
    from validation.population_contract import contract
    (tmp_path/'docs/program').mkdir(parents=True)
    (tmp_path/'validation/protocols').mkdir(parents=True)
    registry = {'entries': {'V08': {'contract': contract()}}}
    (tmp_path/'validation/protocols.json').write_text(json.dumps(registry))
    (tmp_path/'validation/protocols/v08_protocol.md').write_text('test-local protocol')
    runtime = {'test_local_runtime': True}
    phase = {'kind': 'population_finite_phase_v1', 'source_digest': 'test_source',
             'registry_sha256': campaign.digest(tmp_path/'validation/protocols.json'),
             'registry_entry_sha256': canonical_digest(registry['entries']['V08']),
             'protocol_sha256': campaign.digest(tmp_path/'validation/protocols/v08_protocol.md'),
             'contract': contract(), 'runtime': runtime, 'allocation': campaign.allocation(),
             'resource_authorization': 'standing_user_bounded_local_known_answer_execution',
             'run_name': 'test-run'}
    path = tmp_path/'phase.json'
    path.write_text(json.dumps(phase))
    program = {'decisions': [{'id': 'D-PROTOCOL-T2', 'status': 'accepted'}],
               'continuation': {'steps': [{'id': 'T2-POP/PROTOCOL-FREEZE', 'state': 'complete'}]},
               'protocol_phase_bindings': {'tier2': 'test'},
               'evidence': [{'id': 'test', 'path': 'phase.json', 'sha256': campaign.digest(path)}]}
    register = tmp_path/'docs/program/program.json'
    register.write_text(json.dumps(program))
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    monkeypatch.setattr(campaign, 'source_digest', lambda: 'test_source')
    monkeypatch.setattr(campaign, 'require_runtime', lambda: runtime)
    assert campaign.require_phase()['run_path'] == str(tmp_path/'validation/artifacts/V08/test-run')
    for key, value in [('source_digest', 'wrong'), ('runtime', {}), ('allocation', {}),
                       ('contract', {}), ('run_name', '../outside')]:
        changed = {**phase, key: value}
        path.write_text(json.dumps(changed))
        program['evidence'][0]['sha256'] = campaign.digest(path)
        register.write_text(json.dumps(program))
        with pytest.raises(ValueError):
            campaign.require_phase()
