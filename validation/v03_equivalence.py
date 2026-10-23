"""Narrow, source-bound equivalence lemmas; unknown mutations stay in scope."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.metadata
import inspect
import math
from pathlib import Path
import struct
import textwrap

RULES = ("builtin_nan_case_v1", "full_population_slice_v1", "unused_gp_stack_v1", "tpe_replay_copy_v1", "gp_invalidated_cache_v1", "pasha_empty_interval_v1", "pasha_falsey_report_default_v1", "pasha_reversal_flag_v1", "pasha_latest_comparison_v1", "cmaes_scalar_config_copy_v1", "local_falsey_guard_v1", "gp_library_default_v1", "gp_tensor_construction_v1", "gp_unused_batch_argument_v1", "tpe_unused_bookkeeping_v1", "replay_unused_batch_default_v1", "replay_empty_promotion_queue_v1")
RULES += ("modern_gp_kernel_flag_v1", "modern_gp_training_axis_v1")
RULES += ("ray_terminal_retry_bound_v1",)
RULES += ("study_cancelled_reaggregation_v1",)
RULES += ("modern_gp_admitted_guard_v1", "modern_gp_scalar_view_v1",
          "study_restore_controller_copy_v1", "study_restore_falsey_default_v1")
CONTEXTS = {
    "hponas/study.py": "c101c8e07ffe65fa4b0e73453c76f9f4a1d1f78e81def22c54e7bd1043897d16",
    "hponas/executors/ray_executor.py": "f9c7a7967608ba06794913157479cc72ad852a783d8a3cd05048c432e9c9532f",
    "hponas/searchers/gp_searcher.py": "78804381622efd55de8ec363d770457a143cfef9d72edff38083ea149eb92be7",
    "hponas/schedulers.py": "22a00c3c288fe5759c709c6e0407d49f26dc72913ad1cc9b7083366b51baac8c",
    "hponas/searchers_gp.py": "d94fa38d591f5a59e3bc43a62808f969d8a6a29a9681a4d73013a3de038e1a12",
    "hponas/searchers_tpe.py": "47b92a56fe1018525eeb44450dbee9bba6fe020f1a58e5be71a7a5086375978b",
    "hponas/searchers/cmaes_searcher.py": "5fb40c8def5908e2640d8529297ef968ad4b5aa303982659834a59382d05ccc0",
    "hponas/executors/base.py": "b80776437f88595bc7a3b3ccd00c0c5e6076e265d68563788e209df7f695c6a7",
    "hponas/replay.py": "59658c7dd15c9933eb26a66b64b276d1be5921bf3510cfb036c6c05a84d42688",
}
CONTEXT_DEPENDENCIES = {
    "study_cancelled_reaggregation_v1": {'hponas/evaluation.py': 'f949e23c292ab94822ad79955bb87450e0936d1681a9fdae565b7f93b7923aba', 'hponas/study_mo.py': 'a4f2720fc7183be6d437b7a81a73f960868c9220dcf658b335bfc782c7539206', 'hponas/multi_objective.py': 'afee087d5622a6017ceaffc924f5ca0d4062032e8a174367dd97eaf451b1b42a', 'hponas/types.py': '0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304'},
    "modern_gp_training_axis_v1": {
        "hponas/encoding.py": "54675a16db37aacbd2d7b9f04d67916a775fb3b867e81fcc76047818fb8b6ac0",
        "hponas/space.py": "8c508dc0bd1ef8962433ace32f5a89a4fc3c693e661c74d31a787001494aa1f8",
        "hponas/types.py": "0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304",
    },
    "cmaes_scalar_config_copy_v1": {
        "hponas/encoding.py": "54675a16db37aacbd2d7b9f04d67916a775fb3b867e81fcc76047818fb8b6ac0",
        "hponas/types.py": "0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304",
    },
}
CONTEXT_DEPENDENCIES.update({'modern_gp_admitted_guard_v1': {'hponas/encoding.py': '54675a16db37aacbd2d7b9f04d67916a775fb3b867e81fcc76047818fb8b6ac0', 'hponas/space.py': '8c508dc0bd1ef8962433ace32f5a89a4fc3c693e661c74d31a787001494aa1f8', 'hponas/types.py': '0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304', 'hponas/capabilities.py': '5aa5a71637f92e295da4558c646bb84e9b5d9d59f5f683630a344958684faa6a'}, 'modern_gp_scalar_view_v1': {'hponas/encoding.py': '54675a16db37aacbd2d7b9f04d67916a775fb3b867e81fcc76047818fb8b6ac0', 'hponas/space.py': '8c508dc0bd1ef8962433ace32f5a89a4fc3c693e661c74d31a787001494aa1f8', 'hponas/types.py': '0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304', 'hponas/capabilities.py': '5aa5a71637f92e295da4558c646bb84e9b5d9d59f5f683630a344958684faa6a'}, 'study_restore_controller_copy_v1': {'hponas/evaluation.py': 'f949e23c292ab94822ad79955bb87450e0936d1681a9fdae565b7f93b7923aba', 'hponas/budgets.py': '2af2a3c6b046f8f57f2344ef947a225b48d4fb8f3071ce86b635482ca72d3d5b', 'hponas/study_mo.py': 'a4f2720fc7183be6d437b7a81a73f960868c9220dcf658b335bfc782c7539206', 'hponas/multi_objective.py': 'afee087d5622a6017ceaffc924f5ca0d4062032e8a174367dd97eaf451b1b42a', 'hponas/types.py': '0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304'}, 'study_restore_falsey_default_v1': {'hponas/evaluation.py': 'f949e23c292ab94822ad79955bb87450e0936d1681a9fdae565b7f93b7923aba', 'hponas/budgets.py': '2af2a3c6b046f8f57f2344ef947a225b48d4fb8f3071ce86b635482ca72d3d5b', 'hponas/study_mo.py': 'a4f2720fc7183be6d437b7a81a73f960868c9220dcf658b335bfc782c7539206', 'hponas/types.py': '0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304'}})
# Protocol 2.26: concrete streaming restore/aggregation and TPE registration
# are part of these arguments. Bind them before enabling successor proofs.
for _rule in ("study_cancelled_reaggregation_v1", "study_restore_controller_copy_v1",
              "study_restore_falsey_default_v1"):
    CONTEXT_DEPENDENCIES[_rule]["hponas/evaluation_streaming.py"] = (
        "e266a977bc7adce82dfcb13aa4f8e6e349d7d5b205d1185c4825ee14afcabb75")
CONTEXT_DEPENDENCIES["tpe_replay_copy_v1"] = {
    "hponas/types.py": "0b7e28ba19bded3a8211d03e883aeaa468ba1635a35eb9e4cac622bc86638304",
}
RUNTIME_CONTEXTS = {
    "modern_gp_scalar_view_v1": {"torch": "2.13.0"},
    "modern_gp_kernel_flag_v1": {"botorch": "0.18.1", "gpytorch": "1.15.2", "torch": "2.13.0"},
    "modern_gp_training_axis_v1": {"torch": "2.13.0", "numpy": "2.5.2"},
    "gp_library_default_v1": {"scipy": "1.18.1", "gpytorch": "1.15.2"},
    "gp_tensor_construction_v1": {"torch": "2.13.0", "scipy": "1.18.1", "numpy": "2.5.2"},
}

# New public support calls must preserve the same state relations as the
# reviewed concrete searchers; changed helper behavior invalidates the proof.
for _rule in ("unused_gp_stack_v1", "tpe_replay_copy_v1", "gp_invalidated_cache_v1",
              "cmaes_scalar_config_copy_v1", "local_falsey_guard_v1",
              "gp_library_default_v1", "gp_tensor_construction_v1",
              "gp_unused_batch_argument_v1", "tpe_unused_bookkeeping_v1",
              "modern_gp_kernel_flag_v1", "modern_gp_training_axis_v1"):
    CONTEXT_DEPENDENCIES.setdefault(_rule, {})["hponas/capabilities.py"] = (
        "5aa5a71637f92e295da4558c646bb84e9b5d9d59f5f683630a344958684faa6a")



def verify_proof_source_contexts(root):
    """Reject stale reviewed source before spending a complete campaign.

    Certificate verification remains mandatory at closure. This preflight
    checks that every prospectively enabled source-bound rule is applicable to
    the candidate's actual source, independently of its historical test fixture.
    """
    expected = dict(CONTEXTS)
    for dependencies in CONTEXT_DEPENDENCIES.values():
        for path, digest in dependencies.items():
            if path in expected and expected[path] != digest:
                raise ValueError(f"Conflicting V03 proof source context: {path}")
            expected[path] = digest
    mismatches = []
    for name, digest in sorted(expected.items()):
        path = Path(root) / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            mismatches.append(name)
    if mismatches:
        raise ValueError("V03 proof source context differs from reviewed candidate: " + ", ".join(mismatches))


def _single_expression_rewrite(original, mutated, before, after):
    """Require exactly one occurrence of an exact expression substitution."""
    old = ast.parse(before, mode="eval").body
    new = ast.parse(after, mode="eval").body

    class Replace(ast.NodeTransformer):
        def __init__(self):
            self.count = 0

        def visit(self, node):
            if _dump(node) == _dump(old):
                self.count += 1
                return copy.deepcopy(new)
            return super().visit(node)

    transform = Replace()
    result = transform.visit(copy.deepcopy(original))
    return transform.count == 1 and _dump(result) == _dump(mutated)


def _one_of_two_expression_rewrite(original, mutated, before, after):
    """Change exactly one of two reviewed sites, with the rest identical.

    Used only for the source-bound Study vector flag's two truth projections.
    A simultaneous change at both sites is not an individual mutation proof.
    """
    old = ast.parse(before, mode="eval").body
    new = ast.parse(after, mode="eval").body
    if sum(_dump(node) == _dump(old) for node in ast.walk(original)) != 2:
        return False
    for selected in range(2):
        class Replace(ast.NodeTransformer):
            def __init__(self):
                self.count = 0

            def visit(self, node):
                if _dump(node) == _dump(old):
                    index = self.count
                    self.count += 1
                    if index == selected:
                        return copy.deepcopy(new)
                return super().visit(node)

        if _dump(Replace().visit(copy.deepcopy(original))) == _dump(mutated):
            return True
    return False


def _dump(node):
    return ast.dump(node, include_attributes=False)


def _normalized(function, name):
    function = copy.deepcopy(function)
    function.name = name
    # Mutmut changes docstring indentation. No rule observes source/docstrings.
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)
            and isinstance(function.body[0].value.value, str)):
        function.body.pop(0)
    return function


def generated_function(binding, span, expected_name):
    path = Path(binding["path"])
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding["sha256"]:
        raise ValueError("Changed generated mutant source")
    start, end = span
    lines = data.decode().splitlines(keepends=True)
    if not (type(start) is int and type(end) is int and 1 <= start <= end <= len(lines)):
        raise ValueError("Invalid generated function span")
    parsed = ast.parse(textwrap.dedent("".join(lines[start - 1:end])))
    if (len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.FunctionDef)
            or parsed.body[0].name != expected_name):
        raise ValueError("Generated function does not match mutant identity")
    return parsed.body[0]


def lemma(original, mutated, module_source, source_path, class_name):
    """Return a proved rule only for a single exact supported transformation."""
    if _dump(original) == _dump(mutated):
        return None  # No blanket identity/introspection claim.
    shadowed = any(
        isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == "float"
        or isinstance(n, ast.arg) and n.arg == "float"
        or isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == "float"
        or isinstance(n, ast.alias) and (n.asname or n.name) == "float"
        for n in ast.walk(ast.parse(module_source)))

    class NanCase(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if (isinstance(node.func, ast.Name) and node.func.id == "float"
                    and len(node.args) == 1 and not node.keywords
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and node.args[0].value.lower() == "nan"):
                node.args[0].value = "nan"
            return node

    if (not shadowed and math.isnan(float("nan"))
            and struct.pack("!d", float("nan")) == struct.pack("!d", float("NAN"))
            and _dump(NanCase().visit(copy.deepcopy(original))) == _dump(NanCase().visit(copy.deepcopy(mutated)))):
        return "builtin_nan_case_v1"

    if hashlib.sha256(module_source.encode()).hexdigest() != CONTEXTS.get(source_path):
        return None
    if (source_path == "hponas/study.py" and class_name == "Study"
            and original.name == "load_checkpoint"):
        if any(_single_expression_rewrite(original, mutated,
               "copy.deepcopy(self." + field + ")", "copy.copy(self." + field + ")")
               for field in ("_evaluation", "_resources")):
            return "study_restore_controller_copy_v1"
        for before, after in (
            ("state.get('finished', False)", "state.get('finished', None)"),
            ("state.get('finished', False)", "state.get('finished')"),
            ("getattr(self, '_vector_objectives', False)", "getattr(self, '_vector_objectives', None)"),
        ):
            # The finished default occurs twice in load_checkpoint. Only the
            # restore call's keyword is covered; the later live assignment is not.
            if before.startswith("state.get"):
                old_call = next(n for n in ast.walk(original) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == 'restore'
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == 'restored_evaluation')
                changed_call = copy.deepcopy(old_call)
                keyword = next(k for k in changed_call.keywords if k.arg == 'finished')
                if _dump(keyword.value) != _dump(ast.parse(before, mode='eval').body):
                    continue
                keyword.value = ast.parse(after, mode='eval').body
                accepted = _single_expression_rewrite(original, mutated,
                    ast.unparse(old_call), ast.unparse(changed_call))
            else:
                accepted = _one_of_two_expression_rewrite(original, mutated, before, after)
            if accepted:
                return "study_restore_falsey_default_v1"
    if (source_path == "hponas/study.py" and class_name == "Study"
            and original.name == "_accept"
            and any(_single_expression_rewrite(original, mutated,
                "result.status != 'cancelled'", "result.status != " + repr(value))
                for value in ("XXcancelledXX", "CANCELLED"))):
        return "study_cancelled_reaggregation_v1"
    if (source_path == "hponas/executors/ray_executor.py" and class_name == "RayExecutor"
            and original.name == "_execute_streaming"
            and _single_expression_rewrite(original, mutated,
                "range(self.max_retries + 1)", "range(self.max_retries + 2)")):
        return "ray_terminal_retry_bound_v1"
    if (source_path == "hponas/searchers/gp_searcher.py" and class_name == "GPSearcher"
            and original.name == "_suggest_joint_impl"):
        predicate = "count > 1 and any(k.kind != 'continuous' or k.condition is not None for k in as_knob_space(self.search_space).knobs)"
        alternatives = (
            "count > 2 and any(k.kind != 'continuous' or k.condition is not None for k in as_knob_space(self.search_space).knobs)",
            "count > 1 and any(k.kind != 'continuous' and k.condition is not None for k in as_knob_space(self.search_space).knobs)",
        )
        if any(_single_expression_rewrite(original, mutated, predicate, other) for other in alternatives):
            return "modern_gp_admitted_guard_v1"
        message = 'Joint mixed GP batches require a bounded finite domain'
        if any(_single_expression_rewrite(original, mutated,
               'ValueError('+repr(message)+')', 'ValueError('+repr(other)+')')
               for other in (None, 'XX'+message+'XX', message.lower(), message.upper())):
            return "modern_gp_admitted_guard_v1"
        if _single_expression_rewrite(original, mutated,
                'acq_value.reshape(-1)[0]', 'acq_value.reshape(+1)[0]'):
            return "modern_gp_scalar_view_v1"
        if _single_expression_rewrite(original, mutated,
                "get_covar_module_with_dim_scaled_prior(ard_num_dims=X_train.shape[-1], use_rbf_kernel=False)",
                "get_covar_module_with_dim_scaled_prior(ard_num_dims=X_train.shape[-1], use_rbf_kernel=None)"):
            return "modern_gp_kernel_flag_v1"
        if _single_expression_rewrite(original, mutated, "X_train.shape[-1]", "X_train.shape[+1]"):
            return "modern_gp_training_axis_v1"
    if (source_path == "hponas/replay.py" and class_name == "ReplayEngine"
            and original.name == "verify_determinism"):
        expected = ast.parse("promotion_queue = []").body[0]
        for index, statement in enumerate(original.body):
            if _dump(statement) == _dump(expected):
                changed = copy.deepcopy(original)
                changed.body[index].value = ast.Constant(None)
                if _dump(changed) == _dump(mutated):
                    return "replay_empty_promotion_queue_v1"
    if (source_path == "hponas/replay.py" and class_name == "ReplayEngine"
            and original.name == "verify_determinism"
            and original.args.args[-1].arg == "batch_size"
            and len(original.args.defaults) == 1
            and _dump(original.args.defaults[0]) == _dump(ast.Constant(1))
            and not any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                        and n.id == "batch_size" for n in ast.walk(original))):
        changed = copy.deepcopy(original)
        changed.args.defaults[0] = ast.Constant(2)
        if _dump(changed) == _dump(mutated):
            return "replay_unused_batch_default_v1"
    if source_path == "hponas/searchers_tpe.py" and class_name == "TPESearcher":
        unused = {"_n_proposed", "_n_observed", "_next_trial_id"}
        read = any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)
                   and n.attr in unused for n in ast.walk(ast.parse(module_source)))
        pairs = {
            "__init__": [("self._n_proposed = 0", "self._n_proposed = 1"),
                         ("self._n_observed = 0", "self._n_observed = 1"),
                         ("self._next_trial_id = 0", "self._next_trial_id = None"),
                         ("self._next_trial_id = 0", "self._next_trial_id = 1")],
            "propose": [("self._n_proposed += n", "self._n_proposed = n"),
                        ("self._n_proposed += n", "self._n_proposed -= n")],
            "_tell": [("self._n_observed += 1", "self._n_observed = 1"),
                        ("self._n_observed += 1", "self._n_observed -= 1"),
                        ("self._n_observed += 1", "self._n_observed += 2")],
        }
        if not read:
            for before, after in pairs.get(original.name, []):
                for index, statement in enumerate(original.body):
                    if _dump(statement) == _dump(ast.parse(before).body[0]):
                        changed = copy.deepcopy(original)
                        changed.body[index] = ast.parse(after).body[0]
                        if _dump(changed) == _dump(mutated):
                            return "tpe_unused_bookkeeping_v1"
    local_flags = {
        ("hponas/executors/base.py", None, "evaluate_trial"): "streamed",
        ("hponas/searchers_gp.py", "GPqLogEISearcher", "observe"): "finite",
        ("hponas/searchers_gp.py", "GPqLogEISearcher", "_validate_controls"): "valid_beta",
    }
    flag = local_flags.get((source_path, class_name, original.name))
    if flag:
        expected = ast.parse(f"{flag} = False").body[0]
        occurrences = [n for n in ast.walk(original) if _dump(n) == _dump(expected)]
        if len(occurrences) == 1:
            class FalseyFlag(ast.NodeTransformer):
                def visit_Assign(self, node):
                    if _dump(node) == _dump(expected):
                        node.value = ast.Constant(None)
                    return node
            if _dump(FalseyFlag().visit(copy.deepcopy(original))) == _dump(mutated):
                return "local_falsey_guard_v1"
    if source_path == "hponas/searchers_gp.py" and class_name == "GPqLogEISearcher":
        if original.name == "_build_gp":
            if _single_expression_rewrite(original, mutated,
                    "torch.stack(self._Y).unsqueeze(-1)", "torch.stack(self._Y).unsqueeze(+1)"):
                return "gp_tensor_construction_v1"
            from gpytorch.kernels import MaternKernel
            if (inspect.signature(MaternKernel).parameters["nu"].default == 2.5
                    and _single_expression_rewrite(original, mutated,
                        "MaternKernel(nu=2.5, ard_num_dims=self._dim, lengthscale_prior=lengthscale_prior)",
                        "MaternKernel(ard_num_dims=self._dim, lengthscale_prior=lengthscale_prior)")):
                return "gp_library_default_v1"
        if original.name == "_propose":
            from scipy.stats import qmc
            if (inspect.signature(qmc.Sobol).parameters["scramble"].default is True
                    and _single_expression_rewrite(original, mutated,
                        "qmc.Sobol(d=self._dim, scramble=True, seed=self.seed)",
                        "qmc.Sobol(d=self._dim, seed=self.seed)")):
                return "gp_library_default_v1"
            cls = next(n for n in ast.parse(module_source).body
                       if isinstance(n, ast.ClassDef) and n.name == class_name)
            acquisition = next(n for n in cls.body
                               if isinstance(n, ast.FunctionDef) and n.name == "_build_acqf")
            if (not any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                        and n.id == "batch_size" for n in ast.walk(acquisition))
                    and _single_expression_rewrite(original, mutated,
                        "self._build_acqf(batch_size=n)", "self._build_acqf(batch_size=None)")):
                return "gp_unused_batch_argument_v1"
            expressions = [("torch.tensor(point, dtype=torch.float64)", "torch.tensor(point, dtype=None)"),
                           ("torch.tensor(point, dtype=torch.float64)", "torch.tensor(point)")]
            for constructor in ("zeros", "ones"):
                expressions.extend((f"torch.{constructor}(self._dim, dtype=torch.float64)", replacement)
                                   for replacement in (f"torch.{constructor}(self._dim, dtype=None)",
                                                       f"torch.{constructor}(self._dim)"))
            if any(_single_expression_rewrite(original, mutated, old, new) for old, new in expressions):
                return "gp_tensor_construction_v1"
    if source_path == "hponas/schedulers.py" and class_name == "PASHAScheduler":
        if original.name == "report" and any(_single_expression_rewrite(
                original, mutated, 'self._resource_reports.get(trial_id, {})', after)
                for after in ('self._resource_reports.get(trial_id, None)',
                              'self._resource_reports.get(trial_id)')):
            return "pasha_falsey_report_default_v1"
        if original.name == "_update_epsilon":
            expected = ast.parse("reversed_once = False").body[0]
            matches = [n for n in ast.walk(original) if _dump(n) == _dump(expected)]
            if len(matches) == 1:
                class Flag(ast.NodeTransformer):
                    def visit_Assign(self, node):
                        if _dump(node) == _dump(expected):
                            node.value = ast.Constant(None)
                        return node
                if _dump(Flag().visit(copy.deepcopy(original))) == _dump(mutated):
                    return "pasha_reversal_flag_v1"
            if _single_expression_rewrite(original, mutated, "r < latest", "r <= latest"):
                return "pasha_latest_comparison_v1"
    if (source_path == "hponas/searchers/cmaes_searcher.py" and class_name == "CMAESSearcher"
            and original.name == "suggest"):
        expected = ast.parse("copy.deepcopy(config.values)", mode="eval").body
        occurrences = [n for n in ast.walk(original) if _dump(n) == _dump(expected)]
        for position in range(len(occurrences)):
            class ScalarCopy(ast.NodeTransformer):
                def __init__(self):
                    self.index = 0

                def visit_Call(self, node):
                    if _dump(node) == _dump(expected):
                        if self.index == position:
                            node.func.attr = "copy"
                        self.index += 1
                    return self.generic_visit(node)
            if _dump(ScalarCopy().visit(copy.deepcopy(original))) == _dump(mutated):
                return "cmaes_scalar_config_copy_v1"
    if (source_path == "hponas/schedulers.py" and class_name == "PASHAScheduler"
            and original.name == "_update_epsilon"):
        expected = ast.parse("if comparison_top <= 0:\n    return").body[0]
        for index, statement in enumerate(original.body):
            if _dump(statement) == _dump(expected):
                changed = copy.deepcopy(original)
                changed.body[index].test.ops = [ast.Lt()]
                if _dump(changed) == _dump(mutated):
                    return "pasha_empty_interval_v1"
    if (source_path == "hponas/searchers_gp.py" and class_name == "GPqLogEISearcher"
            and original.name in {"__init__", "observe", "load_state_dict"}):
        for index, statement in enumerate(original.body):
            if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                    and isinstance(statement.targets[0], ast.Attribute)
                    and isinstance(statement.targets[0].value, ast.Name)
                    and statement.targets[0].value.id == "self"
                    and statement.targets[0].attr in {"_model", "_acqf"}
                    and isinstance(statement.value, ast.Constant) and statement.value.value is None):
                changed = copy.deepcopy(original)
                changed.body[index].value = ast.Constant("")
                if _dump(changed) == _dump(mutated):
                    return "gp_invalidated_cache_v1"
    if source_path == "hponas/schedulers.py" and (class_name, original.name) in {
            ("ASHAScheduler", "_legacy_promote"), ("BudgetedASHAScheduler", "promote"),
            ("MOASHAScheduler", "promote")}:
        # Bound source proves n_pop=len(pop), ranking length<=len(pop), and the
        # bound has exactly one load, in that full-population slice.
        loads = [n for n in ast.walk(original) if isinstance(n, ast.Name)
                 and isinstance(n.ctx, ast.Load) and n.id == "n_promote"]
        bounds = [n.upper for n in ast.walk(original) if isinstance(n, ast.Slice)
                  and n.lower is None and n.step is None and isinstance(n.upper, ast.Name)
                  and n.upper.id == "n_promote"]
        for node in ast.walk(original):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "n_promote"
                    and isinstance(node.value, ast.Name) and node.value.id == "n_pop"
                    and len(loads) == len(bounds) == 1):
                changed = copy.deepcopy(original)
                for candidate in ast.walk(changed):
                    if _dump(candidate) == _dump(node):
                        candidate.value = ast.Constant(None)
                if _dump(changed) == _dump(mutated):
                    return "full_population_slice_v1"
    if (source_path == "hponas/searchers_gp.py" and class_name == "GPqLogEISearcher"
            and original.name == "_build_acqf"
            and not any(isinstance(n, ast.Name) and n.id == "X_train" and isinstance(n.ctx, ast.Load)
                        for n in ast.walk(original))):
        for index, statement in enumerate(original.body):
            expected = ast.parse("X_train = torch.stack(self._X)").body[0]
            if _dump(statement) == _dump(expected):
                changed = copy.deepcopy(original)
                changed.body[index].value = ast.Constant(None)
                if _dump(changed) == _dump(mutated):
                    return "unused_gp_stack_v1"
    if (source_path == "hponas/searchers_tpe.py" and class_name == "TPESearcher"
            and original.name == "load_state_dict"):
        expected = ast.parse('copy.deepcopy(state["events"])', mode="eval").body
        for index, statement in enumerate(original.body):
            if isinstance(statement, ast.For) and _dump(statement.iter) == _dump(expected):
                changed = copy.deepcopy(original)
                changed.body[index].iter.func.attr = "copy"
                if _dump(changed) == _dump(mutated):
                    return "tpe_replay_copy_v1"
    return None


def verify_certificate(certificate, root):
    """Check source context and actual generated code before applying a lemma."""
    mid = certificate["id"]
    module, generated_name = mid.rsplit(".", 1)
    source_path = module.replace(".", "/") + ".py"
    if certificate.get("source_path") != source_path:
        raise ValueError("Equivalent mutant source identity differs")
    source = (Path(root) / source_path).read_text()
    if hashlib.sha256(source.encode()).hexdigest() != certificate.get("source_sha256"):
        raise ValueError("Equivalent mutant proof context is stale")
    original_name = generated_name.split("__mutmut_", 1)[0] + "__mutmut_orig"
    generated_original = generated_function(certificate["generated_source"], certificate["original_span"], original_name)
    generated_mutated = generated_function(certificate["generated_source"], certificate["mutated_span"], generated_name)
    mangled = generated_name.split("__mutmut_", 1)[0]
    if mangled.startswith("xǁ"):
        _, class_name, name = mangled.split("ǁ")
    else:
        class_name, name = None, mangled.removeprefix("x_")
    tree = ast.parse(source)
    scope = tree if class_name is None else next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    actual = next((n for n in scope.body if isinstance(n, ast.FunctionDef) and n.name == name), None) if scope else None
    original = _normalized(generated_original, name)
    mutated = _normalized(generated_mutated, name)
    if actual is None or _dump(_normalized(actual, name)) != _dump(original):
        raise ValueError("Generated original differs from bound source function")
    rule = lemma(original, mutated, source, source_path, class_name)
    if rule is None or rule != certificate.get("rule"):
        raise ValueError("No valid equivalence lemma for this exact mutant")
    for path, expected_hash in CONTEXT_DEPENDENCIES.get(rule, {}).items():
        if hashlib.sha256((Path(root) / path).read_bytes()).hexdigest() != expected_hash:
            raise ValueError("Changed equivalence dependency context")
    for package, expected_version in RUNTIME_CONTEXTS.get(rule, {}).items():
        if importlib.metadata.version(package) != expected_version:
            raise ValueError("Changed equivalence runtime context")
    if rule == "modern_gp_kernel_flag_v1":
        from botorch.models.utils.gpytorch_modules import get_covar_module_with_dim_scaled_prior
        library_source = inspect.getsource(get_covar_module_with_dim_scaled_prior)
        if hashlib.sha256(library_source.encode()).hexdigest() != "2c7f23593e161ee41734c687d91c9ceed5c0370c21abf49f43c2c53d7eae9f08":
            raise ValueError("Changed equivalence library source context")
    if rule == "gp_tensor_construction_v1":
        import torch
        if torch.get_default_dtype() not in {torch.float16, torch.bfloat16, torch.float32, torch.float64}:
            raise ValueError("Unsupported equivalence tensor default dtype")
    return rule
