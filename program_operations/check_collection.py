#!/usr/bin/python3 -I
"""Reject reviewed unsafe test collection patterns without importing test code.

This conservative AST check covers direct imported and local calls, aliases,
decorators, defaults and class bodies. It is not a dynamic Python safety proof.
"""
import ast
import json
from pathlib import Path
import sys

ROOT = Path('/home/ubuntu/workspace/hponas')
REFERENCE_CALLS = {
    'workloads.stylized.case_specs', 'validation.stats.Cluster',
    'validation.tier1_contract.slots', 'validation.v03_equivalence.RUNTIME_CONTEXTS',
    'validation.v03_equivalence.CONTEXT_DEPENDENCIES',
}


def collection_calls(source):
    tree = ast.parse(source)
    imports = {}
    local = {n.name: n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            imports.update({a.asname or a.name: (node.module or '') + '.' + a.name
                            for a in node.names})
        elif isinstance(node, ast.Import):
            imports.update({a.asname or a.name.split('.')[0]:
                            a.name if a.asname else a.name.split('.')[0] for a in node.names})

    def resolve(node):
        if isinstance(node, ast.Name):
            return imports.get(node.id, 'local:' + node.id if node.id in local else '')
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else ''
        return ''

    # Resolve simple callable aliases as well as direct imported names.
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = resolve(node.value)
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name) and value:
                    imports[target.id] = value

    rows = []

    def empty_exception(name, seen=frozenset()):
        if name in {'Exception', 'RuntimeError', 'ValueError', 'TimeoutError'} and name not in imports and name not in local:
            return True
        definition = local.get(name)
        if name in seen or not isinstance(definition, ast.ClassDef):
            return False
        return (not definition.decorator_list and not definition.keywords
                and len(definition.bases) == 1 and isinstance(definition.bases[0], ast.Name)
                and all(isinstance(n, ast.Pass) or (isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))
                    for n in definition.body)
                and empty_exception(definition.bases[0].id, seen | {name}))

    def walk(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            children = [*node.decorator_list, *node.args.defaults,
                        *[v for v in node.args.kw_defaults if v]]
            # Annotations are eager unless future annotations is enabled.
            if not any(isinstance(n, ast.ImportFrom) and n.module == '__future__'
                       and any(a.name == 'annotations' for a in n.names) for n in tree.body):
                children += [a.annotation for a in [*node.args.posonlyargs,
                    *node.args.args, *node.args.kwonlyargs] if a.annotation]
                if node.returns:
                    children.append(node.returns)
        elif isinstance(node, ast.Lambda):
            children = [*node.args.defaults, *[v for v in node.args.kw_defaults if v]]
        elif isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'":
            children = []
        else:
            children = list(ast.iter_child_nodes(node))
        if isinstance(node, ast.Call):
            target = resolve(node.func)
            if target.startswith(('hponas.', 'workloads.', 'validation.', 'local:')):
                allowed = any(target == name or target.startswith(name + '.') for name in REFERENCE_CALLS)
                if target.startswith('local:'):
                    definition = local.get(target.removeprefix('local:'))
                    allowed = isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                        resolve(d) == 'hypothesis.strategies.composite' for d in definition.decorator_list)
                    allowed = allowed or empty_exception(target.removeprefix('local:'))
                rows.append(dict(line=node.lineno, call=ast.unparse(node), target=target,
                                 allowed=allowed))
        for child in children:
            walk(child)

    walk(tree)
    return rows


def main():
    if len(sys.argv) != 1:
        raise ValueError('No arguments accepted')
    files = sorted((ROOT / 'tests').rglob('*.py'))
    rows = [dict(file=str(path.relative_to(ROOT)), **row) for path in files
            for row in collection_calls(path.read_text())]
    failures = [row for row in rows if not row['allowed']]
    print(json.dumps(dict(passed=not failures, files_scanned=len(files),
        reviewed_reference_or_deferred_calls=len(rows) - len(failures), failures=failures,
        scientific_acceptance=False), indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
