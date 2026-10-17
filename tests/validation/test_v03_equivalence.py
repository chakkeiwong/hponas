"""Exclusions require exact semantic transformations and immutable context."""

import ast
import copy
import hashlib
import json
import textwrap

import pytest

from tools.source_identity import ROOT
from validation.v03_equivalence import (
    CONTEXTS, CONTEXT_DEPENDENCIES, RUNTIME_CONTEXTS, _normalized, lemma,
    verify_certificate,
)
from validation.v03_mutation_testing import _binding


def proof_source(path):
    # Mutmut instruments hponas in its copied checkout. The proof-checker tests
    # exercise the independently bound reviewed source; the production verifier
    # still compares actual generated functions with each campaign's source.
    fixture = ROOT / "tests/fixtures/v03_equivalence" / (path.split("/")[-1] + ".txt")
    assert _binding(fixture)["sha256"] == CONTEXTS[path]
    return fixture.read_text()


@pytest.mark.parametrize("case,accepted", [
    ("case", True), ("wrong_value", False), ("shadow", False),
    ("changed_result", False), ("changed_generated", False), ("wrong_id", False), ("stale_source", False),
])
def test_nan_lemma_binds_real_generated_function_and_refuses_nearby_changes(tmp_path, case, accepted):
    source = 'def f():\n    return float("nan")\n'
    if case == "shadow":
        source = 'float = lambda x: x\n' + source
    directory = tmp_path / "hponas"
    directory.mkdir()
    actual = directory / "example.py"
    actual.write_text(source)
    generated = tmp_path / "generated.py"
    transformed = 'float("NAN")' if case != "wrong_value" else 'float("inf")'
    if case == "changed_result":
        transformed = 'str(float("NAN"))'
    generated.write_text('def x_f__mutmut_orig():\n    return float("nan")\n'
                         f'def x_f__mutmut_1():\n    return {transformed}\n')
    certificate = {"id": "hponas.example.x_f__mutmut_1", "rule": "builtin_nan_case_v1",
                   "source_path": "hponas/example.py", "source_sha256": _binding(actual)["sha256"],
                   "generated_source": _binding(generated), "original_span": [1, 2], "mutated_span": [3, 4]}
    if case == "changed_generated":
        generated.write_text(generated.read_text().replace('"NAN"', '"inf"'))
    elif case == "wrong_id":
        certificate["id"] = "hponas.example.x_f__mutmut_2"
    elif case == "stale_source":
        actual.write_text(source + "# changed\n")
    if accepted:
        assert verify_certificate(certificate, tmp_path) == "builtin_nan_case_v1"
    else:
        with pytest.raises(ValueError):
            verify_certificate(certificate, tmp_path)


@pytest.mark.parametrize("klass,name", [("ASHAScheduler", "_legacy_promote"),
                                      ("BudgetedASHAScheduler", "promote"), ("MOASHAScheduler", "promote")])
def test_full_slice_proof_requires_bound_ranking_and_exact_single_change(klass, name):
    path = "hponas/schedulers.py"
    source = proof_source(path)
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == klass)
    original = _normalized(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name), name)
    changed = copy.deepcopy(original)
    for node in ast.walk(changed):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id == "n_pop":
            node.value = ast.Constant(None)
    assert lemma(original, changed, source, path, klass) == "full_population_slice_v1"
    assert lemma(original, changed, source + "\n# unreviewed ranking", path, klass) is None
    changed.body.append(ast.parse("return []").body[0])
    assert lemma(original, changed, source, path, klass) is None


def test_unused_stack_proof_requires_exact_public_state_context_and_no_other_change():
    path = "hponas/searchers_gp.py"
    source = proof_source(path)
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "GPqLogEISearcher")
    original = _normalized(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_build_acqf"), "_build_acqf")
    changed = copy.deepcopy(original)
    for node in ast.walk(changed):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "X_train" for t in node.targets):
            node.value = ast.Constant(None)
    assert lemma(original, changed, source, path, cls.name) == "unused_gp_stack_v1"
    assert lemma(original, changed, source + "\n# changed observation contract", path, cls.name) is None
    changed.body.append(ast.parse("self._X.clear()").body[0])
    assert lemma(original, changed, source, path, cls.name) is None


def test_unproved_real_arithmetic_rewrite_is_not_an_equivalence_rule():
    original = ast.parse("def f(n, eta):\n    return max(1, __import__('math').ceil(n/eta))").body[0]
    changed = ast.parse("def f(n, eta):\n    return max(2, __import__('math').ceil(n/eta))").body[0]
    assert lemma(original, changed, ast.unparse(original), "hponas/schedulers.py", None) is None


@pytest.mark.parametrize("method,accepted", [("load_state_dict", True), ("state_dict", False), ("observe", False)])
def test_tpe_copy_proof_is_limited_to_read_only_replay_of_serialized_events(method, accepted):
    path = "hponas/searchers_tpe.py"
    source = proof_source(path)
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "TPESearcher")
    original = _normalized(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method), method)
    changed = copy.deepcopy(original)
    for node in ast.walk(changed):
        if isinstance(node, ast.Attribute) and node.attr == "deepcopy":
            node.attr = "copy"
    expected = "tpe_replay_copy_v1" if accepted else None
    assert lemma(original, changed, source, path, cls.name) == expected
    assert lemma(original, changed, source + "\n# changed retention behavior", path, cls.name) is None
    changed.body.append(ast.parse('self._events = state["events"]').body[0])
    assert lemma(original, changed, source, path, cls.name) is None


PROSPECTIVE_CASES = json.loads((ROOT / "tests/fixtures/v03_equivalence/prospective_cases.json").read_text())


@pytest.mark.parametrize('kind',['reachable_scalar_guard','finished_true','live_finished_assignment',
                                  'searcher_copy','retained_controller'])
def test_recovery_proofs_refuse_nearby_observable_changes(kind):
    path='hponas/searchers/gp_searcher.py' if kind=='reachable_scalar_guard' else 'hponas/study.py'
    klass='GPSearcher' if kind=='reachable_scalar_guard' else 'Study'
    name='_suggest_joint_impl' if kind=='reachable_scalar_guard' else 'load_checkpoint'
    source=proof_source(path)
    scope=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name==klass)
    original=_normalized(next(n for n in scope.body if isinstance(n,ast.FunctionDef) and n.name==name),name)
    mutated=copy.deepcopy(original)
    if kind=='reachable_scalar_guard':
        target=next(n for n in ast.walk(mutated) if isinstance(n,ast.Compare)
            and isinstance(n.left,ast.Name) and n.left.id=='count' and isinstance(n.ops[0],ast.Gt))
        target.ops=[ast.GtE()]
    elif kind=='finished_true':
        call=next(n for n in ast.walk(mutated) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and n.func.attr=='restore'
            and isinstance(n.func.value,ast.Name) and n.func.value.id=='restored_evaluation')
        next(k for k in call.keywords if k.arg=='finished').value.args[1]=ast.Constant(True)
    elif kind=='live_finished_assignment':
        statement=next(n for n in mutated.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Attribute) and t.attr=='_finished' for t in n.targets))
        statement.value.args[1]=ast.Constant(None)
    else:
        target_name='restored_searcher' if kind=='searcher_copy' else 'restored_evaluation'
        statement=next(n for n in mutated.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id==target_name for t in n.targets))
        if kind=='searcher_copy':statement.value.func.attr='copy'
        else:statement.value=statement.value.args[0]
    assert lemma(original,mutated,source,path,klass) is None


def prepared_certificate(tmp_path, case):
    path = case["source_path"]
    actual = tmp_path / path
    actual.parent.mkdir(parents=True, exist_ok=True)
    actual.write_text(proof_source(path))
    for dependency, expected in CONTEXT_DEPENDENCIES.get(case["rule"], {}).items():
        fixture = ROOT / "tests/fixtures/v03_equivalence" / (dependency.split("/")[-1] + ".txt")
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == expected
        destination = tmp_path / dependency
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(fixture.read_bytes())
    old = textwrap.dedent(case["original"]).rstrip() + "\n"
    new = textwrap.dedent(case["mutated"]).rstrip() + "\n"
    generated = tmp_path / "generated.py"
    generated.write_text(old + new)
    count = len(old.splitlines())
    return {"id": case["id"], "rule": case["rule"], "source_path": path,
            "source_sha256": _binding(actual)["sha256"], "generated_source": _binding(generated),
            "original_span": [1, count], "mutated_span": [count + 1, count + len(new.splitlines())]}


@pytest.mark.parametrize("case", PROSPECTIVE_CASES, ids=lambda c: c["id"])
@pytest.mark.parametrize("damage", [None, "extra_change", "source_change", "wrong_class"])
def test_prospective_rules_require_exact_generated_transformation(tmp_path, case, damage):
    certificate = prepared_certificate(tmp_path, case)
    if damage is None:
        assert verify_certificate(certificate, tmp_path) == case["rule"]
        return
    path = case["source_path"]
    source = proof_source(path)
    mangled = case["id"].rsplit(".", 1)[-1].split("__mutmut_", 1)[0]
    if mangled.startswith("xǁ"):
        _, klass, name = mangled.split("ǁ")
    else:
        klass, name = None, mangled.removeprefix("x_")
    original = _normalized(ast.parse(textwrap.dedent(case["original"])).body[0], name)
    mutated = _normalized(ast.parse(textwrap.dedent(case["mutated"])).body[0], name)
    if damage == "extra_change":
        mutated.body.append(ast.parse("raise RuntimeError('additional change')").body[0])
    elif damage == "source_change":
        source += "\n# changed contract\n"
    else:
        klass = "UnreviewedClass"
    assert lemma(original, mutated, source, path, klass) is None


@pytest.mark.parametrize("case,package", [
    (case, package) for case in PROSPECTIVE_CASES for package in RUNTIME_CONTEXTS.get(case["rule"], {})
], ids=lambda item: item["id"] if isinstance(item, dict) else item)
def test_prospective_runtime_rules_refuse_changed_package_versions(tmp_path, monkeypatch, case, package):
    from validation import v03_equivalence as checker

    certificate = prepared_certificate(tmp_path, case)
    version = checker.importlib.metadata.version
    monkeypatch.setattr(checker.importlib.metadata, "version", lambda name: "changed" if name == package else version(name))
    with pytest.raises(ValueError, match="runtime context"):
        verify_certificate(certificate, tmp_path)


@pytest.mark.parametrize("case,path", [
    (case, path) for case in PROSPECTIVE_CASES for path in CONTEXT_DEPENDENCIES.get(case["rule"], {})
], ids=lambda item: item["id"] if isinstance(item, dict) else item)
def test_prospective_copy_rule_refuses_changed_scalar_encoding(tmp_path, case, path):
    certificate = prepared_certificate(tmp_path, case)
    dependency = tmp_path / path
    dependency.write_text(dependency.read_text() + "\n# changed scalar domain\n")
    with pytest.raises(ValueError, match="dependency context"):
        verify_certificate(certificate, tmp_path)


def test_tensor_rule_refuses_unsupported_runtime_default_dtype(tmp_path, monkeypatch):
    import torch

    case = next(c for c in PROSPECTIVE_CASES if c["rule"] == "gp_tensor_construction_v1")
    certificate = prepared_certificate(tmp_path, case)
    monkeypatch.setattr(torch, "get_default_dtype", lambda: torch.int64)
    with pytest.raises(ValueError, match="default dtype"):
        verify_certificate(certificate, tmp_path)


def test_modern_kernel_rule_refuses_library_changes_even_if_version_is_unchanged(tmp_path, monkeypatch):
    from validation import v03_equivalence as checker

    case = next(c for c in PROSPECTIVE_CASES if c["rule"] == "modern_gp_kernel_flag_v1")
    certificate = prepared_certificate(tmp_path, case)
    monkeypatch.setattr(checker.inspect, "getsource", lambda function: "changed library implementation")
    with pytest.raises(ValueError, match="library source context"):
        verify_certificate(certificate, tmp_path)


def copy_reviewed_contexts(root):
    paths = set(CONTEXTS)
    for dependencies in CONTEXT_DEPENDENCIES.values():
        paths.update(dependencies)
    for name in paths:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        fixture = ROOT / "tests/fixtures/v03_equivalence" / (name.split("/")[-1] + ".txt")
        target.write_bytes(fixture.read_bytes())
    return paths


@pytest.mark.parametrize("damage", [None, "scheduler", "dependency", "missing", "fixture_only"])
def test_proof_context_preflight_checks_actual_source_not_only_historical_fixtures(tmp_path, damage):
    from validation.v03_equivalence import verify_proof_source_contexts

    copy_reviewed_contexts(tmp_path)
    if damage in {"scheduler", "fixture_only"}:
        actual = tmp_path / "hponas/schedulers.py"
        if damage == "fixture_only":
            fixture = tmp_path / "tests/fixtures/v03_equivalence/schedulers.py.txt"
            fixture.parent.mkdir(parents=True)
            fixture.write_bytes(actual.read_bytes())
        actual.write_text(actual.read_text() + "\n# unreviewed source change\n")
    elif damage == "dependency":
        actual = tmp_path / "hponas/encoding.py"
        actual.write_text(actual.read_text() + "\n# changed scalar domain\n")
    elif damage == "missing":
        (tmp_path / "hponas/schedulers.py").unlink()
    if damage is None:
        verify_proof_source_contexts(tmp_path)
    else:
        with pytest.raises(ValueError, match="proof source context"):
            verify_proof_source_contexts(tmp_path)


def test_campaign_rejects_stale_proof_context_before_calibration_or_workers(tmp_path, monkeypatch):
    from validation import v03_mutation_testing as mutation

    copy_reviewed_contexts(tmp_path)
    for name in ("pyproject.toml", "requirements.txt", "validation/protocols.json", "validation/protocols/v03_protocol.md"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    # Populate declared paths so the independent ownership checks do not mask
    # the precise proof-context defect this regression is intended to expose.
    for module in mutation.IN_SCOPE_MODULES:
        path = tmp_path / (module.replace(".", "/") + ".py")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
    actual = tmp_path / "hponas/schedulers.py"
    actual.write_text(actual.read_text() + "\n# changed constructor\n")
    monkeypatch.setattr(mutation, "library_ownership", lambda root: [])
    monkeypatch.setattr(mutation, "prepare_mutation_workspace", lambda: tmp_path)
    monkeypatch.setattr(mutation, "calibrate_isolation", lambda *args: pytest.fail("Calibration must not launch"))
    monkeypatch.setattr(mutation, "_run_with_deadline", lambda *args, **kwargs: pytest.fail("Workers must not launch"))
    with pytest.raises(ValueError, match="proof source context.*hponas/schedulers.py"):
        mutation.run_mutmut()
    assert not (tmp_path / "execution-freeze.json").exists()
