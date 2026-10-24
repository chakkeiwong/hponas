"""DOC-01 exhaustive inventory plus explicit retained semantic evidence.

This does not equate file presence with correct behavior. Atomic behavioral
reconstruction and scientific results remain separate bound evidence.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]


def read(name):return json.loads((ROOT/name).read_text())


def binding(name):
    p=ROOT/name
    return {'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def run(destination):
    from tools.source_identity import source_digest
    original=read('archive/program-2026-10-24/before-doc-01/docs/program/program.json')
    current=read('docs/program/program.json')
    evidence={row['id']:row for row in original['evidence']}
    owners={row['id']:row for row in original['work_items']}
    trace=read(evidence[original['semantic_product_trace']]['path'])
    gap=read('docs/program/gap_closure.json')
    package=read(evidence[original['final_product_qualification']]['path'])
    assert source_digest(ROOT)==package['source_digest']
    mismatches=[]
    for row in current['source_inputs']+current['evidence']:
        if binding(row['path'])['sha256']!=row['sha256']:mismatches.append(row['path'])
    assert not mismatches,mismatches
    rows=[]
    for req in original['requirements']:
        work=[owners[k] for k in req['work_items']]
        semantic=[{'group':group,**row} for group,items in trace['groups'].items() for row in items
                  if row['source_key']==req['id'] or req['id']==row['source_key']
                  or group=='interface_clauses' and set(req['work_items'])&set(row['owners'])]
        paths=sorted({p for w in work for p in w['code_refs']})
        tests=sorted({p for w in work for p in w['test_refs']})
        refs=sorted({e for w in work for e in w['evidence_refs']})
        rows.append({'id':req['id'],'title':req['title'],'historical_disposition':req['disposition'],
                     'reason':req.get('reason'),'source_inputs':[binding(p) for p in req['sources']],
                     'owners':[{'id':w['id'],'state':w['state'],'implementation':w['implementation'],
                                'done_when':w['done_when'],'next_action':w['next_action']} for w in work],
                     'owner_code':[binding(p) for p in paths], 'owner_tests':[binding(p) for p in tests],
                     'owner_evidence':[evidence[k] for k in refs],
                     'semantic_rows':semantic,
                     'interpretation':'Read historical disposition with current method outcomes and explicit scope amendments. Owner code/evidence is shared, not a claim that every owner path implements this one requirement.'})
    semantic=[]
    for group,items in trace['groups'].items():
        for row in items:
            semantic.append({'group':group,**row,'current_code':[binding(p) for p in row['code_paths']],
                             'current_tests':[binding(p) for p in row['test_paths']]})
    final=read(gap['final_audit']['path'])
    atomic=[]
    for clause in gap['clauses']:
        result=next(x for x in final['clause_results'] if x['id']==clause['id'])
        reconstruction=read(result['reconstruction']['path'])
        assert result['passed'] and all(c['passed'] and c['observed']==c['expected'] for c in reconstruction['checks'])
        for bound in result['code']+result['tests']:
            assert binding(bound['path'])==bound
        atomic.append({**clause,'current_code':[binding(p) for p in clause['code_paths']],
                       'current_tests':[binding(p) for p in clause['test_paths']],
                       'qualified_behavior':result,'independent_reconstruction':reconstruction})
    modules=[]
    for folder in ('hponas','workloads'):
        for path in sorted((ROOT/folder).rglob('*.py')):
            tree=ast.parse(path.read_text());name=str(path.relative_to(ROOT))
            modules.append({**binding(name),'definitions':[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))],
                            'semantic_references':[r['source_key'] for r in semantic if name in r['code_paths']],
                            'atomic_references':[r['id'] for r in atomic if name in r['code_paths']]})
    result={'kind':'doc01-feature-audit-v1','baseline_revision':original['revision'],
            'source_digest':source_digest(ROOT),'requirements':rows,'semantic_rows':semantic,'atomic_clauses':atomic,
            'module_inventory':modules,'counts':{'requirements':len(rows),'semantic_rows':len(semantic),'atomic_clauses':len(atomic),'modules':len(modules)},
            'qualification':evidence[original['final_product_qualification']], 'final_audit':gap['final_audit'],
            'narrative_findings':binding('docs/audits/2026-10-24-product-documentation-audit.md'),
            'outcomes':binding('docs/METHOD_OUTCOMES.md'),
            'checks':{'all_baseline_owners_complete':all(w['state']=='complete' for w in owners.values()),
                      'current_bindings_match':not mismatches,'unchanged_qualified_source':True,
                      'all_atomic_behavior_oracles_retained':True},
            'limits':'Coverage, current byte identity and retained per-clause evidence review. No new broad runtime campaign or exhaustive formal verification of all code; no universal optimizer or production claim.'}
    assert result['counts']['requirements']==123 and result['counts']['semantic_rows']==131 and result['counts']['atomic_clauses']==27
    Path(destination).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,**result['counts'],'source_digest':result['source_digest'],'ledger':destination}))


if __name__=='__main__':run(sys.argv[1])
