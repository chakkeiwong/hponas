"""Independent, hash-pinned scheduler references for validator engineering."""

import ast
import hashlib
from pathlib import Path

REFERENCE_FILES = {
    "hyperband_stopping.py": "6c51776f5a974b88fc17d25372ab1b11cf1e422c4bec55c45f3fd272ba77e026",
    "hyperband_promotion.py": "6e1dce23f38793af42a2878b7ce7473330306fa672f4b2d24faa49d9e356c155",
}
PASHA_REFERENCE = "docs/program/evidence/2026-09-28/spec-01/syne_tune_0_13_pasha_reference.py"
PASHA_SHA256 = "ad21020675c67bccbde38a8b9f2684cbbc379814a1f05c1ac4850eb10663d1b8"


def promotion_reference():
    directory = Path(__file__).resolve().parents[1] / "tests/fixtures/syne_tune_0_13_0"
    namespace = {"__name__": "pinned_syne_tune_reference"}
    for name, expected in REFERENCE_FILES.items():
        path = directory / name
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != expected:
            raise ValueError("Scheduler reference source hash changed")
        tree = ast.parse(source)
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.ImportFrom)
            and node.module == "syne_tune.optimizer.schedulers.hyperband_stopping")]
        exec(compile(tree, str(path), "exec"), namespace)
    return namespace


def pasha_reference(*, canonical_pairs=False):
    """Load pinned PASHA; optional adapter stabilizes unordered-pair traversal.

    The verbatim source uses ordered pair keys while iterating sets at each
    epoch, so Python hash order can double-count a pair. The explicit adapter
    only sorts internal set iteration. It is a deterministic interpretation of
    the pairwise statistic, not a claim of unmodified vendor equivalence.
    """
    namespace = promotion_reference()
    path = Path(__file__).resolve().parents[1] / PASHA_REFERENCE
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != PASHA_SHA256:
        raise ValueError("PASHA reference source hash changed")
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom)
        and node.module == "syne_tune.optimizer.schedulers.hyperband_promotion")]
    exec(compile(tree, str(path), "exec"), namespace)
    if canonical_pairs:
        class SortedSet(set):
            def __iter__(self):
                return iter(sorted(super().__iter__()))

        namespace["set"] = SortedSet
    return namespace


def reference_promotions(values, reference):
    ref = reference["PromotionRungSystem"]([1, 3], [1 / 3, 1 / 3], "loss", "min", "step", 9)
    for tid, value in values:
        ref._rungs[-1].add(reference["PromotionRungEntry"](tid, value))
    output = []
    while candidate := ref.on_task_schedule("unused"):
        output.append([candidate["trial_id"], candidate["milestone"]])
    return output
