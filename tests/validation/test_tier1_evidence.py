"""Adverse end-to-end evidence controls in temporary development directories."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from validation import tier1_campaign as finite
from validation.evidence import decision,digest
from validation.protocol_identity import canonical_id,protocol_path
from validation.run_validation_with_audit import ValidationRunner
from validation.v16_audit_enforcer import V16Enforcer


@pytest.fixture
def development_phase(monkeypatch,tmp_path):
    # This bypass exists only in test-local monkeypatching; production requires
    # the fully bound current-source phase before creating a run directory.
    monkeypatch.setattr(finite,'require_phase',lambda entry:{'development_test':True,
        'run_path':str(tmp_path/entry/'development-test')})
    monkeypatch.setattr(finite,'require_run',lambda *args:None)


@pytest.mark.parametrize('alias,expected',[('v11a','V11a'),('V11B','V11b'),('v_cost','V-COST'),('v04_t1','V04-T1')])
def test_canonical_suffix_is_preserved(alias,expected):
    assert canonical_id(alias)==expected
    assert V16Enforcer(protocol_path(alias)).validation_id==expected


def test_missing_phase_prevents_any_campaign_directory(tmp_path,monkeypatch):
    (tmp_path/'docs/program').mkdir(parents=True)
    (tmp_path/'docs/program/program.json').write_text(json.dumps({'evidence':[]}))
    monkeypatch.setattr(finite,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='not frozen'):
        ValidationRunner('V10',artifact_root=tmp_path/'not-created')
    assert not (tmp_path/'not-created').exists()


def test_finite_campaign_dispatch_and_v16_reconstruct_actual_evidence(tmp_path,development_phase):
    from validation.task_registry import audited_protocol
    from validation.validators.tier1_validator import Tier1FiniteValidator
    result=audited_protocol('v10',artifact_root=tmp_path)
    assert result['verdict']=='PASS' and result['passed']
    directory=Path(result['artifact_run'])
    assert json.loads((directory/'v16_audit.json').read_text())['passed']
    assert Tier1FiniteValidator('v10',directory).audit().passed
    assert not Tier1FiniteValidator('v10').audit().passed
    # Every slot has a durable start, a closed receipt and raw observations.
    assert len((directory/'slot-journal.jsonl').read_text().splitlines())==4
    slots=json.loads((directory/'slots.json').read_text())
    assert len(slots)==2 and all(Path(s['raw']['path']).is_file() for s in slots)
    with pytest.raises(ValueError,match='retired'):
        audited_protocol('V10',artifact_root=tmp_path,smoke=True)


def test_failed_slot_is_retained_without_replacement_and_audited_inconclusive(tmp_path,monkeypatch,development_phase):
    real=finite.execute_slot; calls=[]
    def fail_second(spec,directory):
        calls.append(spec['id'])
        if spec['restore']:
            directory.mkdir(); (directory/'partial-work.json').write_text('{"unknown_work": true}')
            raise RuntimeError('deliberate interrupted work')
        return real(spec,directory)
    monkeypatch.setattr(finite,'execute_slot',fail_second)
    runner=ValidationRunner('V10',artifact_root=tmp_path)
    assert not runner.run(lambda:finite.campaign('V10',runner.run_dir))
    result=json.loads((runner.run_dir/'results.json').read_text())
    assert result['verdict']=='INCONCLUSIVE'
    rows=json.loads((runner.run_dir/'slots.json').read_text())
    assert rows[1]['status']=='incomplete' and 'interrupted' in rows[1]['error']
    assert (runner.run_dir/'slot-001/partial-work.json').is_file()
    assert json.loads((runner.run_dir/'v16_audit.json').read_text())['passed']
    assert calls.count('advisory-recovery')==1


def produce(tmp_path):
    return finite.campaign('V10',tmp_path)


def test_missing_roster_source_change_and_tampered_artifact_fail_closed(tmp_path,monkeypatch,development_phase):
    result=produce(tmp_path)
    monkeypatch.setattr(finite,'source_digest',lambda:'changed')
    with pytest.raises(ValueError,match='freeze'):
        decision('V10',result)
    monkeypatch.undo()
    monkeypatch.setattr(finite,'require_phase',lambda entry:{'development_test':True,
        'run_path':str(tmp_path/entry/'development-test')})
    monkeypatch.setattr(finite,'require_run',lambda *args:None)
    rows=json.loads((tmp_path/'slots.json').read_text())
    (tmp_path/'slots.json').write_text(json.dumps(rows[:-1]))
    with pytest.raises(ValueError,match='artifact'):
        decision('V10',result)
    result['slots']=finite.binding(tmp_path/'slots.json')
    with pytest.raises(ValueError,match='roster'):
        decision('V10',result)


def test_self_consistent_false_promotion_cannot_gain_acceptance(tmp_path,development_phase):
    result=produce(tmp_path)
    rows=json.loads((tmp_path/'slots.json').read_text())
    raw_path=Path(rows[0]['raw']['path']); raw=json.loads(raw_path.read_text())
    raw['events'][4]['promotions'].append(['C',2])
    raw_path.write_text(json.dumps(raw)); rows[0]['raw']=finite.binding(raw_path)
    (tmp_path/'slots.json').write_text(json.dumps(rows));result['slots']=finite.binding(tmp_path/'slots.json')
    receipt=tmp_path/'slot-receipt-000.json';receipt.write_text(json.dumps(rows[0]))
    journal=tmp_path/'slot-journal.jsonl';events=[json.loads(line) for line in journal.read_text().splitlines()]
    events[1]['receipt']=finite.binding(receipt);journal.write_text(''.join(json.dumps(e)+'\n' for e in events))
    result['journal']=finite.binding(journal)
    result.update(verdict='PASS',passed=True)
    assert decision('V10',result)=='FAIL'


def test_old_favorable_results_cannot_satisfy_new_entries():
    from validation.tier1_contract import ENTRIES
    for entry in ENTRIES:
        assert decision(entry,{'schema_version':1,'validation_id':entry,'verdict':'PASS','passed':True})=='INCONCLUSIVE'


def test_tier1_gate_requires_complete_receipts(monkeypatch):
    from tools import tier1_gate
    monkeypatch.setattr(tier1_gate,'check',lambda:([],{'program':{'tier1_campaign_receipts':{}}}))
    report=tier1_gate.evaluate()
    assert not report['passed'] and not report['integrated_release_accepted']


def test_tier1_gate_cannot_accept_receipt_labels_without_reconstruction(tmp_path,monkeypatch):
    from tools import tier1_gate
    from validation.tier1_contract import ENTRIES
    from types import SimpleNamespace
    receipts={}
    for entry in ENTRIES:
        path=tmp_path/entry;path.mkdir()
        (path/'results.json').write_text(json.dumps({'verdict':'PASS','passed':True}))
        receipts[entry]={'run':entry}
    monkeypatch.setattr(tier1_gate,'ROOT',tmp_path)
    monkeypatch.setattr(tier1_gate,'check',lambda:([],{'program':{'tier1_campaign_receipts':receipts}}))
    monkeypatch.setattr(tier1_gate,'require_phase',lambda entry:{'run_path':str(tmp_path/entry)})
    monkeypatch.setattr(tier1_gate,'campaign_view',lambda *args:{'fresh':True})
    bad=SimpleNamespace(passed=False,to_dict=lambda:{'passed':False})
    monkeypatch.setattr(tier1_gate,'V16Enforcer',lambda *args:SimpleNamespace(audit_execution=lambda run:bad))
    report=tier1_gate.evaluate()
    assert not report['passed'] and len(report['criteria'])==8


def test_allocated_run_refuses_alternative_location(tmp_path,monkeypatch):
    monkeypatch.setattr(finite,'require_phase',lambda entry:{'run_path':str(tmp_path/'allocated')})
    finite.require_run('V10',tmp_path/'allocated')
    with pytest.raises(ValueError,match='once-only'):
        finite.require_run('V10',tmp_path/'replacement')
