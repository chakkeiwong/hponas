"""Integrity of the semantic product review; this does not establish science."""
import hashlib
import json
from pathlib import Path

GROUPS = ('interface_clauses','legacy_product_rows','build_v3_components',
          'recovery_approval_items','deferred_dispositions')
STATES = {'development_verified','retained_baseline','excluded','watchlist',
          'failed_cancelled','unqualified_deployment','open'}


def row_key(group, row):
    if group == 'interface_clauses': return row['id']
    if group == 'legacy_product_rows': return str(row['legacy_row'])
    if group == 'build_v3_components': return row['original_tier']+':'+row['component']
    if group == 'recovery_approval_items': return row['requirement']['id']
    return row['requirement']


def read_bound(root, binding):
    path = Path(binding['path'])
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Product trace path escapes workspace')
    path = root/path
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Product trace path escapes workspace')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding['sha256']:
        raise ValueError('Product trace binding differs: '+str(path.relative_to(root)))
    return json.loads(data)


def validate_trace(root, program):
    root = Path(root)
    work = {w['id']:w for w in program['work_items']}
    complete = any(work.get(w,{}).get('state') == 'complete' for w in ('PRD-01','BANK-01'))
    ident = program.get('semantic_product_trace')
    if not ident:
        if complete:
            raise ValueError('Completed product work requires semantic clause evidence')
        return
    evidence = {e['id']:e for e in program['evidence']}
    if ident not in evidence:
        raise ValueError('Unknown semantic product trace evidence')
    trace = read_bound(root,evidence[ident])
    if trace.get('kind') != 'semantic_product_trace_v1' or set(trace['groups']) != set(GROUPS):
        raise ValueError('Unknown or incomplete product trace inventory')
    original = read_bound(root,trace['original_inventory'])
    stages = {s['id']:s for s in program['continuation']['steps']}
    for group in GROUPS:
        expected = {row_key(group,r) for r in original[group]}
        rows = trace['groups'][group]
        keys = [r['source_key'] for r in rows]
        if len(keys) != len(set(keys)) or set(keys) != expected:
            raise ValueError('Missing, duplicate or unknown product clauses: '+group)
        for row in rows:
            name = group+':'+row['source_key']
            if row['status'] not in STATES or not row.get('behavior') or not row.get('scope'):
                raise ValueError('Product clause lacks behavior/scope: '+name)
            if not row['owners'] or not set(row['owners']) <= set(work):
                raise ValueError('Unknown product clause owner: '+name)
            if row['qualification_owner'] not in stages:
                raise ValueError('Unknown product qualification stage: '+name)
            if not row['evidence_refs'] or not set(row['evidence_refs']) <= set(evidence):
                raise ValueError('Missing product clause evidence: '+name)
            for eid in row['evidence_refs']:
                # Evidence may be Markdown or binary; only verify its bytes.
                entry = evidence[eid]
                path = root/entry['path']
                if not path.resolve().is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                    raise ValueError('Product clause evidence bytes differ: '+name)
            if row['status'] == 'development_verified' and (not row['code_paths'] or not row['test_paths']):
                raise ValueError('Development clause lacks code and executable checks: '+name)
            for name in row['code_paths']+row['test_paths']+[row['resource_anchor']]:
                path = root/name
                if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                    raise ValueError('Product clause path missing: '+name)
            if complete and row['status'] == 'open':
                raise ValueError('Completed product work retains an open clause: '+name)
    if work.get('BANK-01',{}).get('state') == 'complete':
        ident = program.get('final_product_qualification')
        if ident not in evidence:
            raise ValueError('Bank product completion lacks current-source qualification')
        package = read_bound(root,evidence[ident])
        from tools.source_identity import source_digest
        if package.get('source_digest') != source_digest(root):
            raise ValueError('Final product qualification is stale')
        # The stage's scientific verifier owns campaign/gate recomputation.
        # This guard only stops omission/staleness from becoming completion.
