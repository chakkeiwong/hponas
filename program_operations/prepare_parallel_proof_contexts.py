"""One-time local preparation; no tests, campaigns or accepted verdicts."""
import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/ubuntu/workspace/hponas')
OLD = ROOT / 'tests/fixtures/v03_equivalence_2026_10_18'
NEW = ROOT / 'tests/fixtures/v03_equivalence_2026_10_26'

def dump(node):
    return ast.dump(node, include_attributes=False)

def normalized(node):
    node = copy.deepcopy(node)
    node.name = 'function'
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body.pop(0)
    return node

def candidates(old, new):
    if isinstance(old, ast.AST) and isinstance(new, ast.AST):
        if dump(old) == dump(new):
            return []
        result = [(old, new)]
        if type(old) is type(new):
            for key, value in ast.iter_fields(old):
                result += candidates(value, getattr(new, key))
        return result
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [pair for a, b in zip(old, new) for pair in candidates(a, b)]
    return []

def main():
    if NEW.exists():
        raise ValueError('Successor fixture directory already exists')
    NEW.mkdir()
    checker = ROOT / 'validation/v03_equivalence.py'
    text = checker.read_text()
    namespace = {}
    exec(compile(text, str(checker), 'exec'), namespace)
    contexts = namespace['CONTEXTS']
    dependencies = namespace['CONTEXT_DEPENDENCIES']
    paths = set(contexts) | {p for d in dependencies.values() for p in d}
    paths.add('hponas/evaluation_parallel.py')
    bindings = {}
    for path in sorted(paths):
        data = (ROOT / path).read_bytes()
        bindings[path] = hashlib.sha256(data).hexdigest()
        (NEW / (Path(path).name + '.txt')).write_bytes(data)
    (NEW / 'predecessor-checker.py.txt').write_text(text)
    cases = json.loads((OLD / 'prospective_cases.json').read_text())
    lineage = json.loads((OLD / 'lineage.json').read_text())
    lineage['kind'] = 'parallel_successor_checker_lineage_v1'
    lineage['predecessor_files'] = [
        {'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(OLD.iterdir()) if p.is_file()]
    for index, case in enumerate(cases):
        old = normalized(ast.parse(case['original']).body[0])
        changed = normalized(ast.parse(case['mutated']).body[0])
        mangled = case['id'].rsplit('.', 1)[1].split('__mutmut_', 1)[0]
        if mangled.startswith('xǁ'):
            _, klass, name = mangled.split('ǁ')
        else:
            klass, name = None, mangled.removeprefix('x_')
        tree = ast.parse((ROOT / case['source_path']).read_text())
        scope = tree if klass is None else next(n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == klass)
        current = normalized(next(n for n in scope.body
            if isinstance(n, ast.FunctionDef) and n.name == name))
        applied = None
        for before, after in candidates(old, changed):
            class Replace(ast.NodeTransformer):
                def visit(self, node):
                    if dump(node) == dump(before):
                        return copy.deepcopy(after)
                    return super().visit(node)
            if (sum(dump(n) == dump(before) for n in ast.walk(old)) == 1
                    and sum(dump(n) == dump(before) for n in ast.walk(current)) == 1
                    and dump(Replace().visit(copy.deepcopy(old))) == dump(changed)):
                successor = Replace().visit(copy.deepcopy(current))
                applied = {'before': ast.unparse(before), 'after': ast.unparse(after)}
                break
        if applied is None:
            raise ValueError('Cannot preserve exact transformation: ' + case['id'])
        old_id = case['id']
        case['id'] = old_id.replace('__mutmut_gap_review_', '__mutmut_parallel_review_')
        current.name = mangled + '__mutmut_orig'
        successor.name = case['id'].rsplit('.', 1)[1]
        case.update(original=ast.unparse(current) + chr(10), mutated=ast.unparse(successor) + chr(10))
        row = lineage['cases'][index]
        row.update(current_id=case['id'], predecessor_id=old_id, exact_transformation=applied)
    for name, value in [('prospective_cases.json', cases), ('lineage.json', lineage),
                        ('reviewed-bindings.json', bindings)]:
        (NEW / name).write_text(json.dumps(value, indent=2) + chr(10))
    # Bind only after the substantive written proof review. Original fixtures
    # and checker bytes above retain the previous contract independently.
    for path, old_hash in contexts.items():
        if old_hash != bindings[path]:
            text = text.replace(old_hash, bindings[path])
    for mapping in dependencies.values():
        for path, old_hash in mapping.items():
            if old_hash != bindings[path]:
                text = text.replace(old_hash, bindings[path])
    marker = '\n\ndef verify_proof_source_contexts(root):'
    addition = '\n# Protocol 2.31: inherited parallel controller dispatch is part of these proofs.\n'
    addition += 'for _rule in ("study_cancelled_reaggregation_v1", "study_restore_controller_copy_v1",\n              "study_restore_falsey_default_v1"):\n'
    addition += '    CONTEXT_DEPENDENCIES[_rule]["hponas/evaluation_parallel.py"] = ' + repr(bindings['hponas/evaluation_parallel.py']) + '\n'
    assert text.count(marker) == 1
    checker.write_text(text.replace(marker, addition + marker))
    print(json.dumps({'cases': len(cases), 'contexts': len(bindings), 'directory': str(NEW)}))

if __name__ == '__main__':
    main()
