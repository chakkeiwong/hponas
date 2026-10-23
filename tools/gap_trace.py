#!/usr/bin/python3 -I
"""Clause/evidence consistency guard; never substitutes for behavioral audit."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CLAUSES = {
    'G01-JOINT','G01-RECOVERY','G02-STREAM','G02-FAILURE','G03-DEFAULT','G03-RESUME',
    'G04-TPE-ASHA','G04-MATRIX','G05-ADAPTER','G05-EVALUATION','G06-MIGRATION',
    'G06-PITR','G06-SCHEDULE','G06-ACCESS','G06-SECURITY','G06-QUOTAS','G06-CAPACITY',
    'G07-RGPE','G07-ELIGIBILITY','G07-OUTCOMES','G08-ADAPTERS','G08-LIMITS',
    'G09-ATOMIC','G09-DOCS','G09-GUARDS','G10-INSTALL','G10-GUIDANCE',
}
CAMPAIGNS = {'V01', 'V02', 'V03', 'V04-T0', 'V05', 'V14', 'V04-T1', 'V06',
             'V09', 'V10', 'V11a', 'V11b', 'V13', 'V-COST', 'V08', 'V07', 'V12'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: '+key)
        result[key] = value
    return result


def bound_json(root, binding):
    return json.loads(bound(root, binding), object_pairs_hook=unique_object)


def exact_bindings(root, bindings, names):
    paths = [b['path'] for b in bindings]
    if len(paths) != len(set(paths)) or set(paths) != set(names):
        raise ValueError('Audit file bindings differ from original clause coverage')
    for binding in bindings:
        bound(root, binding)


def current_receipt(root, binding, digest, operation=None):
    receipt = bound_json(root, binding)
    if (receipt.get('kind') != 'fixed_local_operation_v1' or receipt.get('passed') is not True
            or receipt.get('source_digest') != digest or receipt.get('end_source_digest') != digest
            or operation is not None and receipt.get('operation') != operation):
        raise ValueError('Missing, failed or stale current-source operation evidence')
    checks = receipt.get('checks', [])
    if not checks or any(c['returncode'] != 0 or c['timed_out'] for c in checks):
        raise ValueError('Operation evidence lacks passing executed checks')
    for check in checks:
        if not bound(root, check['log']).strip():
            raise ValueError('Operation evidence lacks retained output')


def validate_qualification(root, binding, digest):
    qualification = bound_json(root, binding)
    if (qualification.get('kind') != 'gap_current_source_qualification_v1'
            or qualification.get('passed') is not True or qualification.get('source_digest') != digest
            or sorted(qualification.get('qualified_clauses', [])) != sorted(CLAUSES)):
        raise ValueError('Current complete gap qualification is missing')
    package = bound_json(root, qualification['scientific_package'])
    if (package.get('kind') != 'integrated_local_source_qualified_package_v1'
            or package.get('source_digest') != digest or set(package.get('campaigns', {})) != CAMPAIGNS
            or set(package.get('gates', {})) != {'tier0', 'tier1', 'V08', 'V07', 'V12'}):
        raise ValueError('Current scientific package is missing or incomplete')
    for vid, campaign in package['campaigns'].items():
        artifacts = {name: bound_json(root, {'path': campaign['run']+'/'+name, 'sha256': sha})
                     for name, sha in campaign['hashes'].items()}
        if set(artifacts) != {'metadata.json', 'results.json', 'v16_audit.json'}:
            raise ValueError('Campaign evidence is incomplete')
        meta, result, audit = (artifacts[name] for name in ('metadata.json', 'results.json', 'v16_audit.json'))
        if (any(doc.get('validation_id') != vid for doc in (meta, result, audit))
                or meta.get('source_digest') != digest or result.get('passed') is not True
                or result.get('verdict') != 'PASS' or audit.get('passed') is not True
                or meta.get('results_sha256') != campaign['hashes']['results.json']):
            raise ValueError('Campaign is failed, stale or not bound to its result')
        checks = audit.get('checks', [])
        if (not checks or any(c.get('passed') is not True for c in checks if c.get('severity') == 'error')
                or not any(c.get('name') == 'Decision Adherence' and c.get('severity') == 'error'
                           and c.get('passed') is True and c.get('message') == 'Recomputed verdict: PASS'
                           for c in checks)):
            raise ValueError('Campaign lacks independent decision reconstruction')
    for binding in package['gates'].values():
        gate = bound_json(root, binding)
        if gate.get('passed') is not True or gate.get('source_digest') != digest:
            raise ValueError('Scientific phase gate is failed or stale')
    receipts = qualification.get('behavior_receipts', [])
    if not receipts:
        raise ValueError('New public behavior has no current executed evidence')
    for receipt in receipts:
        current_receipt(root, receipt, digest)


def validate_behavioral_audit(root, audit, rows, digest):
    if (audit.get('kind') != 'independent_gap_completion_audit_v1'
            or audit.get('source_digest') != digest or audit.get('passed') is not True
            or audit.get('unresolved_required_clauses') != []
            or sorted(audit.get('reviewed_clauses', [])) != sorted(CLAUSES)):
        raise ValueError('Final audit did not close every original behavior on current source')
    results = audit.get('clause_results', [])
    if sorted(r['id'] for r in results) != sorted(CLAUSES):
        raise ValueError('Per-clause behavioral reconstructions are missing or duplicated')
    indexed = {r['id']: r for r in rows}
    for result in results:
        row = indexed[result['id']]
        if (result.get('passed') is not True or result.get('scope') != row['scope']
                or result.get('original_refs') != row['original_refs']):
            raise ValueError('Audit changed the original clause or outcome')
        exact_bindings(root, [result['original_source']], [row['original_source']])
        exact_bindings(root, result['code'], row['code_paths'])
        exact_bindings(root, result['tests'], row['test_paths'])
        reconstruction = bound_json(root, result['reconstruction'])
        if (reconstruction.get('clause') != row['id'] or reconstruction.get('source_digest') != digest
                or not reconstruction.get('method', '').strip() or not reconstruction.get('checks')):
            raise ValueError('Independent behavioral reconstruction missing or stale')
        for check in reconstruction['checks']:
            if (not check.get('name', '').strip() or not check.get('oracle', '').strip()
                    or 'expected' not in check or 'observed' not in check
                    or check['expected'] != check['observed'] or check.get('passed') is not True
                    or not check.get('evidence')):
                raise ValueError('Behavior was not independently reconstructed')
            for binding in check['evidence']:
                if not bound(root, binding).strip():
                    raise ValueError('Empty behavioral evidence')
    current_receipt(root, audit['negative_controls'], digest, 'test-boundaries')


def bound(root, binding):
    name = binding['path']
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not (root/path).resolve().is_relative_to(root.resolve()):
        raise ValueError('Evidence path escapes repository')
    payload = (root/path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != binding['sha256']:
        raise ValueError('Evidence hash differs: '+name)
    return payload


def local_file(root, name):
    path=Path(name)
    if path.is_absolute() or '..' in path.parts or not (root/path).resolve().is_relative_to(root.resolve()):
        raise ValueError('Clause path escapes repository')
    if not (root/path).is_file(): raise ValueError('Missing clause file: '+name)
    return root/path


def validate(data, program, root=ROOT, final=False):
    rows = data['clauses']
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != CLAUSES:
        raise ValueError('Atomic clause inventory omitted, duplicated or changed without review')
    if set(data['original_gap_ids']) != {'G%02d'%i for i in range(1,11)} or set(r['gap'] for r in rows) != set(data['original_gap_ids']):
        raise ValueError('All ten historical gaps must remain represented')
    ordered_steps = program['continuation']['steps']
    steps = {s['id']:s for s in ordered_steps}
    if len(steps) != len(ordered_steps):
        raise ValueError('Duplicate program stage')
    final_id = data['final_stage']
    if final_id != 'GAP-01/FINAL-AUDIT' or final_id not in steps:
        raise ValueError('The last phase must be the independent completion audit')
    if not ordered_steps or ordered_steps[-1]['id'] != final_id:
        raise ValueError('Completion audit is not the last program phase')

    def ancestors(sid, seen=None):
        seen=set() if seen is None else seen
        if sid in seen: raise ValueError('Gap dependency cycle')
        if sid not in steps: raise ValueError('Missing gap dependency')
        result=set(steps[sid]['dependencies'])
        for dep in steps[sid]['dependencies']:
            result |= ancestors(dep, seen | {sid})
        return result

    predecessors=ancestors(final_id)
    for r in rows:
        if r['owner'] not in predecessors or r['owner'] not in steps:
            raise ValueError('Final audit can bypass an owning stage: '+r['id'])
        if not r['required_behavior'].strip():
            raise ValueError('Clause lacks original source or behavior')
        local_file(root,r['original_source'])
        if r['scope'] not in ('required','retained_outcome'):
            raise ValueError('New scope exclusions require prospective review')
        if r['implementation_state'] not in ('planned','in_progress','implemented','not_applicable') or r['qualification_state'] not in ('pending','development_verified','qualified'):
            raise ValueError('Unknown implementation/qualification state')
        for b in r['evidence']: bound(root,b)
        for name in r['code_paths']+r['test_paths']:
            local_file(root,name)
        if final:
            if not r['evidence'] or r['qualification_state']!='qualified':
                raise ValueError('Unqualified clause: '+r['id'])
            if r['scope']=='required' and (r['implementation_state']!='implemented' or not r['code_paths'] or not r['test_paths']):
                raise ValueError('Undelivered required behavior: '+r['id'])
            if r['scope']=='retained_outcome' and not r['outcome']:
                raise ValueError('Missing retained research/evidence outcome')
    if final:
        if any(steps[s]['state']!='complete' for s in predecessors if s.startswith(('GAP-01/','BANK-01/GAP-'))):
            raise ValueError('Gap predecessors remain incomplete')
        if not data['final_audit']: raise ValueError('Independent final behavioral audit missing')
        audit=bound_json(root,data['final_audit'])
        # Reuse the unchanged dependency-free source algorithm, outside import path tricks.
        import importlib.util
        spec=importlib.util.spec_from_file_location('source_identity',root/'tools/source_identity.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        digest = module.source_digest(root)
        validate_behavioral_audit(root, audit, rows, digest)
        validate_qualification(root, data['qualification'], digest)
    return {'passed':True,'clauses':len(rows),'gaps':10,'final':final,'scientific_acceptance':False}


def main():
    if sys.argv[1:] not in (['plan'],['final']): return 2
    try:
        result=validate(json.loads((ROOT/'docs/program/gap_closure.json').read_text(), object_pairs_hook=unique_object),
                        json.loads((ROOT/'docs/program/program.json').read_text(), object_pairs_hook=unique_object),final=sys.argv[1]=='final')
    except (ValueError,KeyError,OSError,TypeError) as exc:
        print(json.dumps({'passed':False,'error':str(exc)}));return 1
    print(json.dumps(result));return 0


if __name__=='__main__': raise SystemExit(main())
