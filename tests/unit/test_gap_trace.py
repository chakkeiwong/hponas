"""Counterexamples to accidental completion of an incomplete historical register."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.gap_trace import validate
from tools.gap_trace import CLAUSES, CAMPAIGNS
from tools.source_identity import source_digest

ROOT=Path(__file__).resolve().parents[2]


def documents(root):
    # Real-register integrity is checked by gap_ops check-plan and its operation
    # controls. Unit counterexamples must also run in an isolated source copy.
    ledger, program, _, _ = synthetic_completion(root)
    return ledger, program


@pytest.mark.parametrize('change',['missing','duplicate','bypass','final','escape','fake_qualification'])
def test_historical_gaps_cannot_be_closed_by_register_counts(change, tmp_path):
    ledger,program=documents(tmp_path)
    if change=='missing':ledger['clauses'].pop()
    if change=='duplicate':ledger['clauses'].append(copy.deepcopy(ledger['clauses'][0]))
    if change=='bypass':ledger['clauses'][0]['owner']='GAP-01/FINAL-AUDIT'
    if change=='final':ledger['final_stage']='GAP-01/INTEGRATION-REVIEW'
    if change=='escape':ledger['clauses'][0]['code_paths']=['/etc/passwd']
    if change=='fake_qualification':
        for row in ledger['clauses']:
            row['implementation_state']='implemented';row['qualification_state']='qualified'
            row['evidence']=[]
    with pytest.raises(ValueError):validate(ledger,program,tmp_path,final=change=='fake_qualification')


def test_atomic_fixture_requires_all_original_gaps_and_last_audit(tmp_path):
    ledger,program=documents(tmp_path)
    result=validate(ledger,program,tmp_path)
    assert result['gaps']==10 and result['clauses']==27
    assert result['scientific_acceptance'] is False


def synthetic_completion(root):
    """A disposable counterexample, with no access to real accepted evidence."""
    for name, payload in {
        'tools/source_identity.py': (ROOT/'tools/source_identity.py').read_text(),
        'hponas/public.py': 'def run(): return 1\n',
        'tests/test_behavior.py': 'def test_behavior(): assert 1 == 1\n',
        'pyproject.toml': '', 'requirements.txt': '', 'validation/protocols.json': '{}',
        'original.md': '\n'.join(sorted(CLAUSES)), 'evidence.txt': 'Arbitrary labels\n',
    }.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
    def binding(name):
        return {'path': name, 'sha256': hashlib.sha256((root/name).read_bytes()).hexdigest()}
    program = {'continuation': {'steps': [
        {'id': 'GAP-01/IMPLEMENT', 'work_item': 'GAP-01', 'dependencies': [], 'state': 'complete'},
        {'id': 'BANK-01/GAP-QUALIFICATION', 'work_item': 'BANK-01',
         'dependencies': ['GAP-01/IMPLEMENT'], 'state': 'complete'},
        {'id': 'GAP-01/FINAL-AUDIT', 'work_item': 'GAP-01',
         'dependencies': ['BANK-01/GAP-QUALIFICATION'], 'state': 'in_progress'},
    ]}}
    ledger = {'clauses': [dict(id=cid, gap=cid.split('-')[0], owner='GAP-01/IMPLEMENT',
        original_source='original.md', required_behavior='Deliver '+cid, scope='required',
        implementation_state='implemented', qualification_state='qualified', outcome=None,
        evidence=[binding('evidence.txt')], code_paths=['hponas/public.py'],
        test_paths=['tests/test_behavior.py'], original_refs=[]) for cid in sorted(CLAUSES)],
        'original_gap_ids': ['G%02d'%i for i in range(1, 11)], 'final_stage': 'GAP-01/FINAL-AUDIT'}
    audit = dict(passed=True, unresolved_required_clauses=[], reviewed_clauses=sorted(CLAUSES),
                 source_digest=source_digest(root))
    (root/'audit.json').write_text(json.dumps(audit))
    ledger['final_audit'] = binding('audit.json')
    return ledger, program, audit, binding


def test_label_only_final_audit_cannot_close_qualified_labels(tmp_path):
    ledger, program, _, _ = synthetic_completion(tmp_path)
    with pytest.raises(ValueError):
        validate(ledger, program, tmp_path, final=True)


def bound_completion(root):
    """Syntactically complete fixture; this never qualifies real behavior."""
    ledger, program, audit, binding = synthetic_completion(root)
    digest = source_digest(root)
    def write(name, value):
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return binding(name)
    results = []
    for row in ledger['clauses']:
        reconstruction = dict(clause=row['id'], source_digest=digest, method='fixture-only arithmetic',
            checks=[dict(name='synthetic fixture', oracle='one equals one', expected=1, observed=1,
                         passed=True, evidence=[binding('evidence.txt')])])
        results.append(dict(id=row['id'], passed=True, scope=row['scope'], original_refs=row['original_refs'],
            original_source=binding('original.md'), code=[binding('hponas/public.py')],
            tests=[binding('tests/test_behavior.py')],
            reconstruction=write('reconstruction/'+row['id']+'.json', reconstruction)))
    log = root/'operation.log'
    log.write_text('Synthetic fixture only: no real scientific execution\n')
    receipt = dict(kind='fixed_local_operation_v1', operation='test-boundaries', source_digest=digest,
        end_source_digest=digest, passed=True,
        checks=[dict(returncode=0, timed_out=False, log=binding('operation.log'))])
    negative = write('operation.json', receipt)
    campaigns = {}
    for vid in sorted(CAMPAIGNS):
        run = 'campaigns/'+vid
        result = write(run+'/results.json', dict(validation_id=vid, passed=True, verdict='PASS'))
        meta = write(run+'/metadata.json', dict(validation_id=vid, source_digest=digest,
                                               results_sha256=result['sha256']))
        v16 = write(run+'/v16_audit.json', dict(validation_id=vid, passed=True, checks=[
            dict(name='Decision Adherence', severity='error', passed=True, message='Recomputed verdict: PASS')]))
        campaigns[vid] = dict(run=run, hashes={'metadata.json': meta['sha256'],
            'results.json': result['sha256'], 'v16_audit.json': v16['sha256']})
    gate = write('gate.json', dict(source_digest=digest, passed=True))
    package = dict(kind='integrated_local_source_qualified_package_v1', source_digest=digest,
                   campaigns=campaigns, gates={k: gate for k in ('tier0', 'tier1', 'V08', 'V07', 'V12')})
    ledger['qualification'] = write('qualification.json', dict(kind='gap_current_source_qualification_v1',
        source_digest=digest, passed=True, qualified_clauses=sorted(CLAUSES),
        scientific_package=write('package.json', package), behavior_receipts=[negative]))
    audit.update(kind='independent_gap_completion_audit_v1', clause_results=results, negative_controls=negative)
    ledger['final_audit'] = write('audit.json', audit)
    return ledger, program, audit, binding, write


def test_structurally_complete_fixture_does_not_claim_scientific_acceptance(tmp_path):
    ledger, program, _, _, _ = bound_completion(tmp_path)
    result = validate(ledger, program, tmp_path, final=True)
    assert result['passed'] and result['final'] and result['scientific_acceptance'] is False


@pytest.mark.parametrize('damage', ['missing_clause', 'duplicate_clause', 'stale_source', 'stale_code',
    'changed_original', 'changed_scope', 'missing_behavior', 'wrong_result', 'empty_evidence',
    'missing_qualification', 'stale_qualification', 'favorable_subset', 'failed_campaign',
    'stale_science', 'failed_gate', 'stale_log', 'failed_negative_controls', 'late_stage', 'incomplete_owner'])
def test_final_audit_refuses_incomplete_stale_or_falsely_closed_evidence(tmp_path, damage):
    ledger, program, audit, binding, write = bound_completion(tmp_path)
    first = audit['clause_results'][0]
    if damage == 'missing_clause': audit['clause_results'].pop()
    elif damage == 'duplicate_clause': audit['clause_results'].append(copy.deepcopy(first))
    elif damage == 'stale_source': audit['source_digest'] = '0'*64
    elif damage == 'stale_code': first['code'][0]['sha256'] = '0'*64
    elif damage == 'changed_original': first['original_source'] = binding('evidence.txt')
    elif damage == 'changed_scope': first['scope'] = 'retained_outcome'
    elif damage in ('missing_behavior', 'wrong_result', 'empty_evidence'):
        path = first['reconstruction']['path']
        reconstruction = json.loads((tmp_path/path).read_text())
        if damage == 'missing_behavior': reconstruction['checks'] = []
        if damage == 'wrong_result': reconstruction['checks'][0]['observed'] = 0
        if damage == 'empty_evidence': reconstruction['checks'][0]['evidence'] = []
        first['reconstruction'] = write(path, reconstruction)
    elif damage == 'missing_qualification': ledger.pop('qualification')
    elif damage == 'stale_qualification':
        q = json.loads((tmp_path/'qualification.json').read_text()); q['source_digest'] = '0'*64
        ledger['qualification'] = write('qualification.json', q)
    elif damage in ('favorable_subset', 'failed_campaign', 'stale_science', 'failed_gate'):
        package = json.loads((tmp_path/'package.json').read_text())
        if damage == 'favorable_subset': package['campaigns'].pop('V03')
        if damage == 'stale_science': package['source_digest'] = '0'*64
        if damage == 'failed_gate':
            package['gates']['tier0'] = write('failed-gate.json', dict(source_digest=source_digest(tmp_path), passed=False))
        if damage == 'failed_campaign':
            campaign = package['campaigns']['V03']
            failed = write(campaign['run']+'/results.json', dict(validation_id='V03', passed=False, verdict='FAIL'))
            campaign['hashes']['results.json'] = failed['sha256']
        q = json.loads((tmp_path/'qualification.json').read_text())
        q['scientific_package'] = write('package.json', package)
        ledger['qualification'] = write('qualification.json', q)
    elif damage == 'stale_log': (tmp_path/'operation.log').write_text('changed')
    elif damage == 'failed_negative_controls':
        receipt = json.loads((tmp_path/'operation.json').read_text()); receipt['passed'] = False
        audit['negative_controls'] = write('operation.json', receipt)
    elif damage == 'late_stage':
        program['continuation']['steps'].append(dict(id='BANK-01/LATER', work_item='BANK-01',
                                                    dependencies=['GAP-01/FINAL-AUDIT'], state='planned'))
    elif damage == 'incomplete_owner': program['continuation']['steps'][0]['state'] = 'in_progress'
    ledger['final_audit'] = write('audit.json', audit)
    with pytest.raises((ValueError, KeyError)):
        validate(ledger, program, tmp_path, final=True)
