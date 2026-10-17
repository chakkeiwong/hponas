"""Prospective, distribution-free sufficient power for bounded rank vectors.

No outcomes are evaluated. A supplied lower mean is an explicit alternative,
never an estimate inferred from a label or a result selected after confirmation.
These calculations do not establish that actual PPO outcomes meet it.
"""

from __future__ import annotations

from functools import lru_cache
import math

from validation.tier0_bounded_mean import bounded_mean_evidence
from validation.tier0_rank_design import rank_components


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Finite {name} required")


@lru_cache(maxsize=128)
def critical_wins(n, magnitude, negative_magnitude, alpha):
    return next((k for k in range(n + 1) if bounded_mean_evidence(
        [magnitude] * k + [-negative_magnitude] * (n - k))["p_value"] <= alpha), None)


def component_power_lower(n, lower_mean, *, magnitude=1.0, negative_magnitude=None, alpha=.025):
    """Sufficient rejection probability for independent Xi in [-a,b].

    Set Yi=(Xi+a)/(a+b). Concavity gives log(1+lambda*x) >=
    Yi*log(1+lambda*b) + (1-Yi)*log(1-lambda*a). Thus if sum Yi >= k,
    the registered mixture is at least its value at k wins and n-k losses.
    For Yi in [0,1], the independent bounded-variable Chernoff
    bound is P(sum Yi < k) <= exp(-n KL(k/n || p)), for p>k/n,
    where average E[Yi]>=p=(lower_mean+a)/(a+b). Convexity of exp and
    AM-GM bound the mgf by the corresponding binomial mgf; iid or a binary
    law is not assumed. At p=1 every Xi=b almost surely, handled exactly.

    This bound is conservative; a zero bound does not prove impossibility.
    Missing lower-bound outcomes must themselves meet the stated mean bound.
    """
    if type(n) is not int or not 1 <= n <= 20:
        raise ValueError("Registered fixed count must be in 1..20")
    negative_magnitude = magnitude if negative_magnitude is None else negative_magnitude
    for value, name in ((lower_mean, "lower mean"), (magnitude, "magnitude"),
                        (negative_magnitude, "negative magnitude"), (alpha, "alpha")):
        _finite(value, name)
    if not 0 < magnitude <= 1 or not 0 < negative_magnitude <= 1 or not 0 < lower_mean <= magnitude or not 0 < alpha < 1:
        raise ValueError("Require a positive alternative within true support and alpha in (0,1)")
    k = critical_wins(n, magnitude, negative_magnitude, alpha)
    if k is None:
        power = 0.0
    elif lower_mean == magnitude:
        power = 1.0
    else:
        q, failure_p = k / n, (magnitude - lower_mean) / (magnitude + negative_magnitude)
        if 1 - q <= failure_p:
            power = 0.0
        else:
            divergence = (q * (math.log(q) - math.log1p(-failure_p)) if q else 0.0) + (
                (1 - q) * math.log((1 - q) / failure_p) if q < 1 else 0.0)
            power = -math.expm1(-n * divergence)
    return {"n": n, "lower_mean_assumption": lower_mean, "magnitude": magnitude,
            "negative_magnitude": negative_magnitude,
            "component_alpha": alpha, "sufficient_wins": k, "power_lower_bound": power}


def prospective_rank_sizing(alternatives, grid, *, target_power=.8, max_n=20):
    """Find smallest sufficient count per entry, conditional on stated means.

    Both entries use alpha/2=.025, sufficient for two-entry Holm regardless of
    their ordering. V04 needs all eight components; a union bound permits any
    dependence among them. Counts are computed before confirmation, within the
    registered cap. No caller-provided SIZED/status/approval field is consumed.
    """
    if target_power != .8 or max_n != 20:
        raise ValueError("Registered power target and count cap must remain .8 and 20")
    if (not isinstance(grid, list) or len(grid) < 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in grid)
            or grid[0] != 0 or grid[-1] != 1 or any(a >= b for a, b in zip(grid, grid[1:]))):
        raise ValueError("Frozen increasing budget grid required")
    expected = {entry: ["/".join(key) for key in rank_components(entry)] for entry in ("V04-T0", "V05")}
    if set(alternatives) != set(expected) or any(set(alternatives[entry]) != set(keys) for entry, keys in expected.items()):
        raise ValueError("All nine registered component alternatives are required")
    entries = {}
    for entry, keys in expected.items():
        rows = []
        for n in range(5, max_n + 1):
            components = {key: component_power_lower(n, alternatives[entry][key],
                magnitude=1 - grid[1] if key.endswith("/anytime_win") else 1.0,
                negative_magnitude=1.0) for key in keys}
            lower = max(0.0, 1 - math.fsum(1 - item["power_lower_bound"] for item in components.values()))
            rows.append({"n": n, "components": components, "joint_power_lower_bound": lower})
        chosen = next((row["n"] for row in rows if row["joint_power_lower_bound"] >= target_power), None)
        entries[entry] = {"conditional_chosen_n": chosen, "feasible_under_bound": chosen is not None, "frontier": rows}
    return {"kind": "prospective_bounded_rank_sizing_v1", "entries": entries, "target_power": target_power,
            "assumptions": ["Independent complete seed vectors under the frozen named-suite design.",
                            "Each actual analysis component, including retained missingness, meets its declared lower mean.",
                            "Anytime lower utilities lie in [-1, 1-grid[1]]: missing evidence may retain -1, while time zero cannot contribute a positive win.",
                            "No operational loss/cost veto; actual campaign power additionally requires evidence about those veto probabilities."],
            "power_scope": "statistical_test_before_operational_vetoes",
            "actual_alternative_established": False, "selects_campaign_count": False,
            "verdict": "INCONCLUSIVE", "certifies_acceptance": False}
