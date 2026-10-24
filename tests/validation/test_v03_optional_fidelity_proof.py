"""Exact source-bound missing-fidelity proof, with adjacent counterexamples."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import textwrap

import pytest

from validation.v03_equivalence import CONTEXTS, _normalized, lemma, verify_certificate

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
PATH = 'hponas/searchers_tpe.py'
SOURCE = FIXTURES / 'v03_equivalence_2026_10_18/searchers_tpe.py.txt'
CASES = json.loads((FIXTURES / 'v03_optional_fidelity_2026_10_23.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
@pytest.mark.parametrize('damage', [None, 'extra', 'source', 'class', 'method', 'wrong_key', 'false_default'])
def test_optional_fidelity_proof_requires_exact_single_rewrite(tmp_path, case, damage):
    source = SOURCE.read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == CONTEXTS[PATH]
    name = 'observe'
    klass = 'TPESearcher'
    original = _normalized(ast.parse(textwrap.dedent(case['original'])).body[0], name)
    mutated = _normalized(ast.parse(textwrap.dedent(case['mutated'])).body[0], name)
    if damage == 'extra':
        mutated.body.append(ast.parse('self._events.clear()').body[0])
    elif damage == 'source':
        source += '\n# unreviewed context\n'
    elif damage == 'class':
        klass = 'OtherSearcher'
    elif damage == 'method':
        original.name = mutated.name = 'observe_result'
    elif damage in ('wrong_key', 'false_default'):
        target = next(n for n in ast.walk(mutated) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'fidelity' for t in n.targets))
        if damage == 'wrong_key':
            target.value.args[0] = ast.Constant('other_fidelity')
        else:
            target.value.args = [ast.Constant('fidelity'), ast.Constant(False)]
    if damage is not None:
        assert lemma(original, mutated, source, PATH, klass) is None
        return
    assert lemma(original, mutated, source, PATH, klass) == 'tpe_optional_fidelity_default_v1'
    actual = tmp_path / PATH
    actual.parent.mkdir(parents=True)
    actual.write_text(source)
    old = textwrap.dedent(case['original']).rstrip() + '\n'
    new = textwrap.dedent(case['mutated']).rstrip() + '\n'
    generated = tmp_path / 'generated.py'
    generated.write_text(old + new)
    certificate = dict(id=case['id'], source_path=PATH, source_sha256=CONTEXTS[PATH],
        rule='tpe_optional_fidelity_default_v1',
        generated_source=dict(path=str(generated), sha256=hashlib.sha256(generated.read_bytes()).hexdigest()),
        original_span=[1, len(old.splitlines())],
        mutated_span=[len(old.splitlines())+1, len((old+new).splitlines())])
    assert verify_certificate(certificate, tmp_path) == 'tpe_optional_fidelity_default_v1'
