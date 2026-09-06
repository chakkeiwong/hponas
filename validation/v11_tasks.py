"""
V11 acceptance task set: frozen tasks, scale bounds, and the two declared priors.

Survey reference: Ch 8 sec:priors, roadmap-10 / ch08-03. Authority:
`validation/protocols.json` entries V11a and V11b.

Both entries declare `task_scope: "acceptance task set (multiple independent tasks)"` and
`scale_bounds: "Per-task, declared in the task registry before data."` This module is that
registry. Everything here is fixed before any campaign data is collected, and the manifest
seals it by digest — `tools/verify_manifest.py` refuses a run whose registry has drifted
from what was sealed.

Three arms per task, as the entries define them:

  no_prior        comparator for both entries: the searcher with `prior_fn=None`
  folklore_prior  V11a's arm — a prior centered on plausible expert advice
  wrong_prior     V11b's arm — a prior centered far from the optimum on purpose

V11a additionally carries a `prior_support_requirement`: "The declared prior must place
nonzero density on the region containing the no-prior arm's optimum, verified and recorded
before the campaign; a prior with zero support there makes the comparison vacuous."
`verify_prior_support` performs and records that check. The nonzero guard from
`hponas.priors` makes the property structural rather than incidental, but the entry asks
for it to be *recorded*, not assumed, so the number goes into the artifact.

Scope note (honest limitation): these objectives are deterministic analytic proxies, in
the style of the existing Tier 0 validators. Replicate-to-replicate variation therefore
comes from optimizer seeds alone, not from workload noise. Real-workload replication is
V04-T1's job, and a confirmatory V11 campaign on production workloads would need noisy
objectives; the estimator, the pairing, and the bounds are unchanged by that substitution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from hponas.priors import GuardedPrior, make_nonzero_guarded_prior
from hponas.space import Knob, SearchSpace
from validation.stats import ScaleBounds

ConfigDict = dict[str, Any]
Objective = Callable[[ConfigDict], float]

#: Prior width as a fraction of each knob's range, in the searcher's own coordinates.
#: 0.15 is deliberately generous: a narrow prior would make V11b a test of how sharply
#: a wrong prior can be stated rather than of whether the method recovers from one.
PRIOR_WIDTH_FRACTION = 0.15


# ---------------------------------------------------------------------------
# Unit-cube coordinates (shared with the searchers)
# ---------------------------------------------------------------------------


def to_unit(space: SearchSpace, config: ConfigDict) -> np.ndarray:
    """
    Map a config's continuous knobs to [0, 1]^d, applying log warping where declared.

    This mirrors `GPqLogEISearcher._to_unit_cube`, so a prior width expressed here means
    the same thing the acquisition function sees. A prior stated in raw units would be
    wildly asymmetric on a log-scaled knob such as a learning rate.
    """
    knobs = [k for k in space.knobs if k.kind == "continuous"]
    out = np.empty(len(knobs), dtype=float)
    for i, knob in enumerate(knobs):
        low, high = knob.bounds
        val = config[knob.name]
        if knob.transform == "log":
            out[i] = (math.log(val) - math.log(low)) / (math.log(high) - math.log(low))
        else:
            out[i] = (val - low) / (high - low)
    return out


def make_gaussian_prior(
    space: SearchSpace,
    center: ConfigDict,
    width: float = PRIOR_WIDTH_FRACTION,
) -> Callable[[ConfigDict], float]:
    """
    Isotropic Gaussian prior in unit-cube coordinates, centered on `center`.

    Returned unguarded: the searchers call `ensure_guarded` at entry, and V11's whole
    point is to exercise their real prior path rather than a pre-processed one.
    """
    if width <= 0.0:
        raise ValueError(f"make_gaussian_prior: width must be positive, got {width}")
    center_u = to_unit(space, center)

    def prior(config: ConfigDict) -> float:
        u = to_unit(space, config)
        quad = float(np.sum(((u - center_u) / width) ** 2))
        return math.exp(-0.5 * quad)

    return prior


# ---------------------------------------------------------------------------
# Task definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptanceTask:
    """
    One frozen acceptance task: space, objective, declared bounds, and both priors.

    `declared_optimum` is the location the folklore prior is built around and the region
    V11a's support requirement is checked against. `wrong_center` is V11b's deliberately
    bad advice, placed far from the optimum in unit-cube distance.
    """

    task_id: str
    space_factory: Callable[[], SearchSpace]
    objective: Objective
    direction: str
    bound_low: float
    bound_high: float
    declared_optimum: ConfigDict
    wrong_center: ConfigDict
    note: str = ""

    @property
    def scale_bounds(self) -> ScaleBounds:
        """The frozen normalization span for this task."""
        return ScaleBounds(low=self.bound_low, high=self.bound_high, direction=self.direction)

    def space(self) -> SearchSpace:
        """A fresh space instance (searchers hold references, so never share one)."""
        return self.space_factory()

    def folklore_prior(self, space: SearchSpace) -> Callable[[ConfigDict], float]:
        return make_gaussian_prior(space, self.declared_optimum)

    def wrong_prior(self, space: SearchSpace) -> Callable[[ConfigDict], float]:
        return make_gaussian_prior(space, self.wrong_center)

    def registry_record(self) -> dict[str, Any]:
        """The manifest's frozen record for this task (enters the registry digest)."""
        return {
            "low": self.bound_low,
            "high": self.bound_high,
            "direction": self.direction,
        }


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------


def _branin(config: ConfigDict) -> float:
    """Branin-Hoo. Three global minima at 0.397887; max 308.13 at (-5, 0)."""
    x, y = config["x"], config["y"]
    a, b, c, r, s, t = 1.0, 5.1 / (4 * math.pi**2), 5.0 / math.pi, 6.0, 10.0, 1.0 / (8 * math.pi)
    return float(a * (y - b * x**2 + c * x - r) ** 2 + s * (1 - t) * math.cos(x) + s)


_HARTMANN3_ALPHA = np.array([1.0, 1.2, 3.0, 3.2])
_HARTMANN3_A = np.array(
    [[3.0, 10.0, 30.0], [0.1, 10.0, 35.0], [3.0, 10.0, 30.0], [0.1, 10.0, 35.0]]
)
_HARTMANN3_P = np.array(
    [
        [0.3689, 0.1170, 0.2673],
        [0.4699, 0.4387, 0.7470],
        [0.1091, 0.8732, 0.5547],
        [0.0381, 0.5743, 0.8828],
    ]
)


def _hartmann3(config: ConfigDict) -> float:
    """Hartmann-3. Global min -3.86278 at (0.114614, 0.555649, 0.852547); max ~0."""
    x = np.array([config["x1"], config["x2"], config["x3"]])
    inner = np.sum(_HARTMANN3_A * (x - _HARTMANN3_P) ** 2, axis=1)
    return float(-np.sum(_HARTMANN3_ALPHA * np.exp(-inner)))


def _rl_return_proxy(config: ConfigDict) -> float:
    """
    Smooth stand-in for a PPO return surface over learning rate, entropy cost, discount.

    Maximized, and bounded in [0, 100]. The ripple term gives it more than one local
    optimum, so a prior-guided searcher is not simply walking a bowl.
    """
    d_lr = (math.log10(config["learning_rate"]) - math.log10(5.51e-4)) / 2.0
    d_ent = (math.log10(config["entropy_cost"]) - math.log10(0.01)) / 1.5
    d_gamma = (config["discount"] - 0.99) / 0.05
    quad = d_lr**2 + d_ent**2 + d_gamma**2
    base = 95.0 * math.exp(-0.5 * quad)
    ripple = 3.0 * math.sin(6.0 * d_lr) * math.exp(-0.25 * quad)
    return float(min(max(base + ripple, 0.0), 100.0))


def _sampler_cost_proxy(config: ConfigDict) -> float:
    """
    Smooth stand-in for HMC step-size / mass-scale tuning cost. Minimized, in [0, 1.05].

    Zero at the well-tuned point, rising to 1 as the sampler detunes, with a small
    oscillation in step size standing in for the step-size / acceptance interaction.
    """
    d_step = math.log10(config["step_size"]) - math.log10(0.1)
    d_mass = math.log10(config["mass_scale"])
    quad = d_step**2 + d_mass**2
    return float(1.0 - math.exp(-0.5 * quad) + 0.05 * (1.0 - math.cos(4.0 * d_step)) / 2.0)


# ---------------------------------------------------------------------------
# Spaces
# ---------------------------------------------------------------------------


def _branin_space() -> SearchSpace:
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(-5.0, 10.0)))
    space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 15.0)))
    return space


def _hartmann3_space() -> SearchSpace:
    space = SearchSpace()
    for name in ("x1", "x2", "x3"):
        space.add_knob(Knob(name=name, kind="continuous", bounds=(0.0, 1.0)))
    return space


def _rl_space() -> SearchSpace:
    space = SearchSpace()
    space.add_knob(
        Knob(
            name="learning_rate",
            kind="continuous",
            bounds=(1e-5, 1e-1),
            transform="log",
            note="PPO Adam step size",
        )
    )
    space.add_knob(
        Knob(
            name="entropy_cost",
            kind="continuous",
            bounds=(1e-4, 1e-1),
            transform="log",
            note="entropy bonus coefficient",
        )
    )
    space.add_knob(
        Knob(name="discount", kind="continuous", bounds=(0.9, 0.999), note="gamma")
    )
    return space


def _sampler_space() -> SearchSpace:
    space = SearchSpace()
    space.add_knob(
        Knob(
            name="step_size",
            kind="continuous",
            bounds=(1e-3, 1.0),
            transform="log",
            note="HMC leapfrog step size",
        )
    )
    space.add_knob(
        Knob(
            name="mass_scale",
            kind="continuous",
            bounds=(1e-2, 1e2),
            transform="log",
            note="diagonal mass matrix scale",
        )
    )
    return space


# ---------------------------------------------------------------------------
# The frozen acceptance set
# ---------------------------------------------------------------------------

V11_ACCEPTANCE_TASKS: dict[str, AcceptanceTask] = {
    "branin_2d": AcceptanceTask(
        task_id="branin_2d",
        space_factory=_branin_space,
        objective=_branin,
        direction="minimize",
        bound_low=0.397887,
        bound_high=308.129,
        declared_optimum={"x": -math.pi, "y": 12.275},
        wrong_center={"x": 7.5, "y": 2.0},
        note="Bounds are the analytic global minimum and the box maximum at (-5, 0).",
    ),
    "hartmann_3d": AcceptanceTask(
        task_id="hartmann_3d",
        space_factory=_hartmann3_space,
        objective=_hartmann3,
        direction="minimize",
        bound_low=-3.86278,
        bound_high=0.0,
        declared_optimum={"x1": 0.114614, "x2": 0.555649, "x3": 0.852547},
        wrong_center={"x1": 0.9, "x2": 0.05, "x3": 0.1},
        note="Bounds are the analytic global minimum and the supremum 0.",
    ),
    "rl_proxy_3d": AcceptanceTask(
        task_id="rl_proxy_3d",
        space_factory=_rl_space,
        objective=_rl_return_proxy,
        direction="maximize",
        bound_low=0.0,
        bound_high=100.0,
        declared_optimum={"learning_rate": 0.001013, "entropy_cost": 0.01, "discount": 0.99},
        wrong_center={"learning_rate": 5e-2, "entropy_cost": 1e-4, "discount": 0.905},
        note="Maximized return proxy; included so the campaign exercises both directions.",
    ),
    "sampler_proxy_2d": AcceptanceTask(
        task_id="sampler_proxy_2d",
        space_factory=_sampler_space,
        objective=_sampler_cost_proxy,
        direction="minimize",
        bound_low=0.0,
        bound_high=1.05,
        declared_optimum={"step_size": 0.1, "mass_scale": 1.0},
        wrong_center={"step_size": 1e-3, "mass_scale": 1e2},
        note="Both knobs log-scaled, so the prior is log-normal in raw units.",
    ),
}

#: Confirmatory seeds. Disjoint from the pilot set by construction
#: (policy.power.pilot_data_reuse = forbidden).
CONFIRMATORY_SEED_BASE = 1000

#: Pilot seeds. `min_pilot` is 5 per arm per side (policy.power.min_pilot).
PILOT_SEED_BASE = 9000


def seed_set(base: int, n: int) -> list[int]:
    """Contiguous seed block starting at `base`."""
    return list(range(base, base + n))


def pilot_seeds(n: int = 5) -> list[int]:
    """Optimizer seeds for the pilot. Never reused confirmatorily."""
    return seed_set(PILOT_SEED_BASE, n)


def confirmatory_seeds(n: int) -> list[int]:
    """Optimizer seeds for the confirmatory campaign."""
    return seed_set(CONFIRMATORY_SEED_BASE, n)


def frozen_task_registry(
    tasks: Optional[dict[str, AcceptanceTask]] = None,
) -> dict[str, dict[str, Any]]:
    """The scale-bounds registry a manifest seals by digest."""
    tasks = tasks if tasks is not None else V11_ACCEPTANCE_TASKS
    return {task_id: task.registry_record() for task_id, task in sorted(tasks.items())}


def scale_bounds_by_task(
    tasks: Optional[dict[str, AcceptanceTask]] = None,
) -> dict[str, ScaleBounds]:
    """Bounds in the form `validation.stats.build_clusters` consumes."""
    tasks = tasks if tasks is not None else V11_ACCEPTANCE_TASKS
    return {task_id: task.scale_bounds for task_id, task in tasks.items()}


# ---------------------------------------------------------------------------
# V11a prior support requirement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriorSupportRecord:
    """
    Evidence that a declared prior does not exclude the optimum's region.

    `density_at_optimum` is the guarded density at the declared optimum;
    `ratio_to_mean` puts it on a scale-free footing by dividing by the guarded prior's
    mean density over the space, so the number means the same thing on every task.
    """

    task_id: str
    arm: str
    density_at_optimum: float
    mean_density: float
    ratio_to_mean: float
    guard_floor: float
    has_support: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "arm": self.arm,
            "density_at_optimum": self.density_at_optimum,
            "mean_density": self.mean_density,
            "ratio_to_mean": self.ratio_to_mean,
            "guard_floor": self.guard_floor,
            "has_support": self.has_support,
        }


def verify_prior_support(
    task: AcceptanceTask,
    arm: str,
    n_samples: int = 2048,
    seed: int = 0,
) -> PriorSupportRecord:
    """
    Verify and record that an arm's prior has nonzero density at the declared optimum.

    Satisfies V11a's `prior_support_requirement`. The check runs against the *guarded*
    prior, because that is what the searchers actually consume: `GPqLogEISearcher` and
    `PriorBandSampler` both call `ensure_guarded` at entry. A wrong prior therefore also
    passes, which is the intended reading — V11b needs the wrong advice to be recoverable,
    and a prior that truly excluded the optimum would make recovery impossible rather than
    merely slow.
    """
    space = task.space()
    if arm == "folklore_prior":
        raw = task.folklore_prior(space)
    elif arm == "wrong_prior":
        raw = task.wrong_prior(space)
    else:
        raise ValueError(
            f"verify_prior_support: arm must be 'folklore_prior' or 'wrong_prior', got {arm!r}"
        )

    guarded: GuardedPrior = make_nonzero_guarded_prior(raw, space, seed=seed)
    density = guarded(task.declared_optimum)

    rng = np.random.default_rng(seed)
    mean_density = float(
        np.mean([guarded(space.sample_config(rng)) for _ in range(n_samples)])
    )

    return PriorSupportRecord(
        task_id=task.task_id,
        arm=arm,
        density_at_optimum=density,
        mean_density=mean_density,
        ratio_to_mean=density / mean_density if mean_density > 0 else float("inf"),
        guard_floor=guarded.floor,
        has_support=density > 0.0,
    )


def verify_all_prior_support(
    tasks: Optional[dict[str, AcceptanceTask]] = None,
) -> list[PriorSupportRecord]:
    """Support records for both prior arms on every acceptance task."""
    tasks = tasks if tasks is not None else V11_ACCEPTANCE_TASKS
    records = []
    for task_id in sorted(tasks):
        for arm in ("folklore_prior", "wrong_prior"):
            records.append(verify_prior_support(tasks[task_id], arm))
    return records
