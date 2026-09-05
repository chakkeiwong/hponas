"""
Statistical core for confirmatory validation campaigns.

Survey reference: Ch 16 (validation). Authority: `validation/protocols.json` — this
module implements exactly what the register's `policy` block declares and nothing else:

  - `policy.scale`: range-normalized differences against pre-declared bounds, sign-flipped
    so positive always means better.
  - `policy.resampling`: paired cluster bootstrap — resample task clusters with
    replacement, then resample complete paired study blocks within each selected cluster,
    retaining arm pairing. Individual trials are never resampled: trials inside a tuning
    run are adaptively selected and are not exchangeable.
  - `policy.confirmatory_families`: per-gate Holm-Bonferroni over decision-bearing tests.
  - `policy.power`: sizing by Monte Carlo simulation under the same two-level hierarchy,
    against the upper 80% confidence bound on the pilot variance, with a declared
    integer maximum sample beyond which the verdict is `inconclusive`.
  - `policy.missingness`: incomplete replicates are excluded with their paired block, and
    loss above 10% in any arm voids the campaign.

Decisions are read off a bootstrap confidence bound at the family-adjusted level, not off
a point estimate. A percentile p-value is reported alongside so the Holm step-down has
something to order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

import numpy as np
from scipy import stats

#: Bootstrap draws for confirmatory intervals (policy.resampling.draws).
DEFAULT_DRAWS = 10_000

#: Family-wise alpha (policy.confirmatory_families.alpha_family).
DEFAULT_ALPHA = 0.05

#: Reduced draw count used inside power simulations only. Sizing needs the *decision*
#: reproduced thousands of times, not a publication-grade interval each time.
SIZING_DRAWS = 999

#: Simulation replicates per candidate sample size (policy.power.method_detail).
SIZING_REPLICATES = 2_000

#: Missingness above this fraction in any arm voids the campaign (policy.missingness).
MISSINGNESS_VOID_FRACTION = 0.10

#: Confidence level for the conservative pilot variance bound
#: (policy.power.pilot_variance_treatment = conservative_ucb).
PILOT_VARIANCE_CONFIDENCE = 0.80

Direction = Literal["minimize", "maximize"]


# ---------------------------------------------------------------------------
# Scale: range normalization against pre-declared bounds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScaleBounds:
    """
    Pre-declared objective range for one task, frozen before data collection.

    Percentage margins are undefined when the baseline objective is zero or negative and
    ambiguous when the denominator is itself estimated in the campaign, so every
    difference is divided by a span fixed in advance (policy.scale).
    """

    low: float
    high: float
    direction: Direction = "minimize"

    def __post_init__(self) -> None:
        if not self.high > self.low:
            raise ValueError(f"ScaleBounds: high ({self.high}) must exceed low ({self.low})")
        if self.direction not in ("minimize", "maximize"):
            raise ValueError(f"ScaleBounds: unknown direction {self.direction!r}")

    @property
    def span(self) -> float:
        """Denominator of every normalized difference on this task."""
        return self.high - self.low

    def normalized_difference(self, arm_value: float, comparator_value: float) -> float:
        """
        Normalized arm-minus-comparator difference, signed so positive means better.

        On a minimized objective a *lower* arm value is an improvement, so the raw
        difference is sign-flipped (policy.scale.direction_normalized).
        """
        raw = (arm_value - comparator_value) / self.span
        return -raw if self.direction == "minimize" else raw


# ---------------------------------------------------------------------------
# Paired blocks and clusters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairedBlock:
    """
    One paired study replicate: arm and comparator on the same task and optimizer seed.

    A block is only usable when every arm in it ran to the declared endpoint under the
    same accounting policy (policy.resampling.pairing_definition). A value of None means
    the replicate did not reach the endpoint; the block is then excluded whole, never
    half-used.
    """

    task: str
    seed: int
    arm_value: Optional[float]
    comparator_value: Optional[float]

    @property
    def complete(self) -> bool:
        """True when both arms reached the declared endpoint."""
        return self.arm_value is not None and self.comparator_value is not None


@dataclass(frozen=True)
class Cluster:
    """Normalized paired differences for one task (the resampling's outer unit)."""

    task: str
    differences: np.ndarray

    @property
    def n_blocks(self) -> int:
        return int(self.differences.size)

    @property
    def mean(self) -> float:
        return float(np.mean(self.differences))


@dataclass(frozen=True)
class MissingnessReport:
    """Accounting for replicates that did not reach the declared endpoint."""

    planned: int
    complete: int
    dropped: tuple[tuple[str, int], ...]

    @property
    def loss_fraction(self) -> float:
        if self.planned == 0:
            return 0.0
        return (self.planned - self.complete) / self.planned

    @property
    def voids_campaign(self) -> bool:
        """Loss above 10% of planned replicates voids the campaign (policy.missingness)."""
        return self.loss_fraction > MISSINGNESS_VOID_FRACTION

    def to_dict(self) -> dict:
        return {
            "planned": self.planned,
            "complete": self.complete,
            "loss_fraction": self.loss_fraction,
            "dropped": [{"task": t, "seed": s} for t, s in self.dropped],
            "voids_campaign": self.voids_campaign,
        }


def build_clusters(
    blocks: Sequence[PairedBlock],
    bounds_by_task: dict[str, ScaleBounds],
) -> tuple[list[Cluster], MissingnessReport]:
    """
    Group paired blocks into per-task clusters of normalized differences.

    Incomplete blocks are excluded with their pairing intact and recorded in the
    missingness report rather than silently dropped.

    Raises:
        KeyError: if a block's task has no pre-declared scale bounds. Normalizing against
            bounds invented after the fact would defeat the point of declaring them.
    """
    by_task: dict[str, list[float]] = {}
    dropped: list[tuple[str, int]] = []

    for block in blocks:
        if block.task not in bounds_by_task:
            raise KeyError(f"No declared scale bounds for task {block.task!r}")
        if not block.complete:
            dropped.append((block.task, block.seed))
            continue
        diff = bounds_by_task[block.task].normalized_difference(
            block.arm_value, block.comparator_value  # type: ignore[arg-type]
        )
        by_task.setdefault(block.task, []).append(diff)

    clusters = [
        Cluster(task=task, differences=np.asarray(diffs, dtype=float))
        for task, diffs in sorted(by_task.items())
    ]
    report = MissingnessReport(
        planned=len(blocks),
        complete=sum(c.n_blocks for c in clusters),
        dropped=tuple(dropped),
    )
    return clusters, report


def cluster_level_mean(clusters: Sequence[Cluster]) -> float:
    """
    The estimand: mean over tasks of the within-task mean paired difference.

    Tasks are weighted equally regardless of how many replicates each carries, because
    the claim is about the task family, not about whichever task happened to run longest.
    """
    if not clusters:
        raise ValueError("cluster_level_mean: no clusters")
    return float(np.mean([c.mean for c in clusters]))


# ---------------------------------------------------------------------------
# Paired cluster bootstrap
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapResult:
    """Bootstrap distribution of the cluster-level paired mean."""

    point: float
    replicates: np.ndarray
    draws: int
    n_clusters: int
    n_blocks: int

    def lower_bound(self, alpha: float) -> float:
        """One-sided lower confidence bound at level 1 - alpha."""
        return float(np.quantile(self.replicates, alpha))

    def upper_bound(self, alpha: float) -> float:
        """One-sided upper confidence bound at level 1 - alpha."""
        return float(np.quantile(self.replicates, 1.0 - alpha))

    def one_sided_p(self, threshold: float) -> float:
        """
        Percentile-bootstrap p-value against the one-sided null `theta <= threshold`.

        The +1 in numerator and denominator keeps the p-value strictly positive: with a
        finite number of draws, "no replicate fell below the threshold" is evidence, not
        proof, so it may not be reported as p = 0.
        """
        below = int(np.count_nonzero(self.replicates <= threshold))
        return (1.0 + below) / (self.draws + 1.0)


def paired_cluster_bootstrap(
    clusters: Sequence[Cluster],
    draws: int = DEFAULT_DRAWS,
    seed: int = 0,
) -> BootstrapResult:
    """
    Two-level bootstrap: resample tasks, then resample paired blocks within each.

    Each (draw, cluster-slot) pair gets its own independent within-cluster resample, so a
    task selected twice in one draw contributes two independent block resamples — the
    correct behavior for a nested bootstrap, and the reason this cannot be collapsed into
    a single per-cluster resample reused across slots.

    Note (policy.resampling.draws_note): the draw count bounds Monte Carlo error of the
    interval, not the cluster count. With a handful of tasks the interval is wide however
    many draws are taken.
    """
    if not clusters:
        raise ValueError("paired_cluster_bootstrap: no clusters")
    if draws < 1:
        raise ValueError(f"paired_cluster_bootstrap: draws must be positive, got {draws}")

    n_clusters = len(clusters)
    rng = np.random.default_rng(seed)

    # Slot (d, j) draws the mean of one independent resample of the chosen cluster.
    slots = draws * n_clusters
    banks = np.empty((n_clusters, slots), dtype=float)
    for c, cluster in enumerate(clusters):
        values = cluster.differences
        idx = rng.integers(0, values.size, size=(slots, values.size))
        banks[c] = values[idx].mean(axis=1)

    chosen = rng.integers(0, n_clusters, size=(draws, n_clusters))
    slot_ids = np.arange(slots).reshape(draws, n_clusters)
    replicates = banks[chosen, slot_ids].mean(axis=1)

    return BootstrapResult(
        point=cluster_level_mean(clusters),
        replicates=replicates,
        draws=draws,
        n_clusters=n_clusters,
        n_blocks=sum(c.n_blocks for c in clusters),
    )


# ---------------------------------------------------------------------------
# One-sided decisions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestResult:
    """
    One entry's confirmatory result, before family correction.

    `threshold` is the decision boundary on the normalized scale: the margin itself for a
    superiority test, and *minus* the margin for a non-inferiority test, since a
    non-inferiority margin is a tolerated shortfall.
    """

    entry_id: str
    test: str
    point: float
    threshold: float
    p_value: float
    bootstrap: BootstrapResult

    def lower_bound(self, alpha: float) -> float:
        return self.bootstrap.lower_bound(alpha)

    def clears(self, alpha: float) -> bool:
        """True when the lower confidence bound at `alpha` sits above the threshold."""
        return self.lower_bound(alpha) > self.threshold

    def to_dict(self, alpha: float = DEFAULT_ALPHA) -> dict:
        return {
            "entry_id": self.entry_id,
            "test": self.test,
            "point_estimate": self.point,
            "threshold": self.threshold,
            "p_value": self.p_value,
            "alpha_used": alpha,
            "lower_bound": self.lower_bound(alpha),
            "clears": self.clears(alpha),
            "n_clusters": self.bootstrap.n_clusters,
            "n_blocks": self.bootstrap.n_blocks,
            "draws": self.bootstrap.draws,
        }


def superiority_one_sided(
    entry_id: str,
    clusters: Sequence[Cluster],
    margin: float = 0.0,
    draws: int = DEFAULT_DRAWS,
    seed: int = 0,
) -> TestResult:
    """
    One-sided superiority of the arm over its comparator by at least `margin`.

    V11a sets margin = 0: any reliable positive gain against no prior justifies
    default-on, so this is ordinary one-sided superiority.
    """
    boot = paired_cluster_bootstrap(clusters, draws=draws, seed=seed)
    return TestResult(
        entry_id=entry_id,
        test="superiority_one_sided",
        point=boot.point,
        threshold=margin,
        p_value=boot.one_sided_p(margin),
        bootstrap=boot,
    )


def non_inferiority_one_sided(
    entry_id: str,
    clusters: Sequence[Cluster],
    margin: float,
    draws: int = DEFAULT_DRAWS,
    seed: int = 0,
) -> TestResult:
    """
    One-sided non-inferiority: the arm is no worse than its comparator by more than
    `margin` on the normalized scale.

    V11b sets margin = 0.10 — the largest range-normalized shortfall under a deliberately
    wrong prior that would still permit shipping priors on by default. It is a product
    tolerance fixed before data, not an estimate read off observed noise.
    """
    if margin <= 0:
        raise ValueError(
            f"non_inferiority_one_sided: margin must be positive, got {margin}. "
            "A zero-margin non-inferiority test is a superiority test."
        )
    boot = paired_cluster_bootstrap(clusters, draws=draws, seed=seed)
    threshold = -margin
    return TestResult(
        entry_id=entry_id,
        test="non_inferiority_one_sided",
        point=boot.point,
        threshold=threshold,
        p_value=boot.one_sided_p(threshold),
        bootstrap=boot,
    )


# ---------------------------------------------------------------------------
# Family correction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HolmDecision:
    """One member's outcome under the family's Holm-Bonferroni step-down."""

    entry_id: str
    p_value: float
    rank: int
    adjusted_alpha: float
    reject: bool

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "p_value": self.p_value,
            "rank": self.rank,
            "adjusted_alpha": self.adjusted_alpha,
            "reject": self.reject,
        }


def holm_bonferroni(
    p_values: dict[str, float],
    alpha: float = DEFAULT_ALPHA,
    family_size: Optional[int] = None,
) -> list[HolmDecision]:
    """
    Holm-Bonferroni step-down over a gate's confirmatory family.

    Args:
        p_values: entry id → one-sided p-value for the members tested now.
        alpha: family-wise error rate.
        family_size: size of the *declared* family, which may exceed the number of
            entries tested in this campaign. The tier-1 gate declares six members; a
            campaign that runs two of them must still correct for six, otherwise the
            family-wise rate is only controlled for whichever subset happened to run
            first. Defaults to the number of p-values supplied.

    Returns:
        Decisions in ascending p-value order. Once a member fails its threshold, every
        larger p-value fails too — that step-down property is what holds the family-wise
        rate at alpha.
    """
    if family_size is not None:
        if family_size < len(p_values):
            raise ValueError(
                f"holm_bonferroni: family_size {family_size} is smaller than the "
                f"{len(p_values)} p-values supplied"
            )
        if family_size < 1:
            raise ValueError(
                f"holm_bonferroni: family_size must be positive, got {family_size}"
            )

    if not p_values:
        return []

    m = family_size if family_size is not None else len(p_values)

    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    decisions: list[HolmDecision] = []
    still_rejecting = True

    for i, (entry_id, p) in enumerate(ordered):
        adjusted = alpha / (m - i)
        if still_rejecting and p <= adjusted:
            reject = True
        else:
            reject = False
            still_rejecting = False
        decisions.append(
            HolmDecision(
                entry_id=entry_id,
                p_value=p,
                rank=i + 1,
                adjusted_alpha=adjusted,
                reject=reject,
            )
        )

    return decisions


# ---------------------------------------------------------------------------
# Sizing by simulation
# ---------------------------------------------------------------------------


def variance_upper_bound(
    values: Sequence[float],
    confidence: float = PILOT_VARIANCE_CONFIDENCE,
) -> float:
    """
    Upper confidence bound on a variance, from the chi-square distribution.

    Sizing against the bound rather than the point estimate means pilot noise inflates
    the confirmatory sample instead of shrinking it
    (policy.power.pilot_variance_treatment).
    """
    arr = np.asarray(values, dtype=float)
    if arr.size < 2:
        raise ValueError("variance_upper_bound: need at least 2 observations")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"variance_upper_bound: confidence must be in (0, 1), got {confidence}")
    dof = arr.size - 1
    s2 = float(np.var(arr, ddof=1))
    return dof * s2 / float(stats.chi2.ppf(1.0 - confidence, dof))


def _bootstrap_means_balanced(
    diffs: np.ndarray,
    draws: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Vectorized two-level bootstrap for a balanced (clusters x blocks) design."""
    n_clusters, n_blocks = diffs.shape
    chosen = rng.integers(0, n_clusters, size=(draws, n_clusters))
    block_idx = rng.integers(0, n_blocks, size=(draws, n_clusters, n_blocks))
    sampled = diffs[chosen[:, :, None], block_idx]
    return sampled.mean(axis=2).mean(axis=1)


def simulate_power(
    effect: float,
    cluster_sd: float,
    block_sd: float,
    n_clusters: int,
    blocks_per_cluster: int,
    threshold: float,
    alpha: float,
    replicates: int = SIZING_REPLICATES,
    draws: int = SIZING_DRAWS,
    seed: int = 0,
) -> float:
    """
    Monte Carlo power for the two-level paired design at a given per-task sample size.

    Data are generated under the entry's own hierarchy — a task-level effect drawn around
    `effect` with spread `cluster_sd`, then paired block differences around each task
    effect with spread `block_sd` — and the decision is the same bootstrap lower-bound
    rule used confirmatorily. Power is not read off a closed-form t-test formula, which
    does not apply to a cluster-level paired estimand (policy.power.method_detail).
    """
    if n_clusters < 1 or blocks_per_cluster < 1:
        raise ValueError("simulate_power: need at least one cluster and one block")
    rng = np.random.default_rng(seed)
    rejections = 0
    for _ in range(replicates):
        task_effects = rng.normal(effect, cluster_sd, size=n_clusters)
        diffs = rng.normal(
            task_effects[:, None], block_sd, size=(n_clusters, blocks_per_cluster)
        )
        boot = _bootstrap_means_balanced(diffs, draws=draws, rng=rng)
        if float(np.quantile(boot, alpha)) > threshold:
            rejections += 1
    return rejections / replicates


@dataclass(frozen=True)
class SizingResult:
    """Outcome of sizing one entry from pilot variance."""

    chosen_n: Optional[int]
    attained_power: float
    power_target: float
    max_sample: int
    curve: tuple[tuple[int, float], ...]

    @property
    def reaches_target(self) -> bool:
        return self.chosen_n is not None

    def to_dict(self) -> dict:
        return {
            "chosen_n": self.chosen_n,
            "attained_power": self.attained_power,
            "power_target": self.power_target,
            "max_sample": self.max_sample,
            "reaches_target": self.reaches_target,
            "curve": [{"blocks_per_cluster": n, "power": p} for n, p in self.curve],
        }


def size_by_simulation(
    effect: float,
    cluster_sd: float,
    block_sd: float,
    n_clusters: int,
    threshold: float,
    alpha: float,
    power_target: float,
    max_sample: int,
    candidates: Optional[Sequence[int]] = None,
    replicates: int = SIZING_REPLICATES,
    draws: int = SIZING_DRAWS,
    seed: int = 0,
) -> SizingResult:
    """
    Smallest per-task replicate count reaching `power_target`, capped at `max_sample`.

    Reaching the cap without clearing is a real outcome, not a prompt to keep going: the
    entry's stopping rule turns it into verdict `inconclusive`
    (policy.power.max_sample_rule).
    """
    grid = sorted(set(candidates)) if candidates else list(range(2, max_sample + 1))
    grid = [n for n in grid if n <= max_sample]
    if not grid:
        raise ValueError("size_by_simulation: empty candidate grid")

    curve: list[tuple[int, float]] = []
    chosen: Optional[int] = None
    attained = 0.0

    for n in grid:
        power = simulate_power(
            effect=effect,
            cluster_sd=cluster_sd,
            block_sd=block_sd,
            n_clusters=n_clusters,
            blocks_per_cluster=n,
            threshold=threshold,
            alpha=alpha,
            replicates=replicates,
            draws=draws,
            seed=seed + n,
        )
        curve.append((n, power))
        attained = power
        if power >= power_target:
            chosen = n
            break

    return SizingResult(
        chosen_n=chosen,
        attained_power=attained,
        power_target=power_target,
        max_sample=max_sample,
        curve=tuple(curve),
    )
