"""Prospective pilot sizing from jointly sufficient vector events.

This preserves the registered component tests and the operational loss veto.
Independence/stationarity is required across vectors, never within a vector.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
import math

from scipy.stats import beta, binom

from validation.tier0_phase_contracts import JOINT_SIZING_POLICY
from validation.tier0_rank_design import rank_components

THRESHOLD = Fraction(84, 125)


@lru_cache(maxsize=256)
def exact_event_e(good, bad, threshold=THRESHOLD):
    """Exact integral of (1+c*lambda)^good * (1-lambda)^bad."""
    if (type(good) is not int or type(bad) is not int or min(good, bad) < 0
            or not 1 <= good + bad <= 20 or not isinstance(threshold, Fraction)
            or not 0 <= threshold <= 1):
        raise ValueError("Exact bounded confirmation event required")
    coefficients = [Fraction(1)]
    for value in [threshold] * good + [Fraction(-1)] * bad:
        updated = [Fraction(0)] * (len(coefficients) + 1)
        for index, coefficient in enumerate(coefficients):
            updated[index] += coefficient
            updated[index + 1] += value * coefficient
        coefficients = updated
    return sum(value / (index + 1) for index, value in enumerate(coefficients))


@lru_cache(maxsize=16)
def required_good_vectors(count):
    """Enough jointly good vectors guarantees every test and the loss cap."""
    if type(count) is not int or not 5 <= count <= 20:
        raise ValueError("Confirmation count must be in 5..20")
    return next((good for good in range(count - count // 10, count + 1)
                 if exact_event_e(good, count - good) >= 40), None)


def good_probability_lower(good, total):
    """One-sided .025 Clopper-Pearson bound; two entries give .95 coverage."""
    if type(good) is not int or type(total) is not int or not 0 <= good <= total or total < 5:
        raise ValueError("Valid complete planned pilot counts required")
    if not good:
        return 0.0
    return math.nextafter(float(beta.ppf(.025, good, total - good + 1)), 0.0)


def optimistic_pilot_completion(total, known_bad):
    """Bound sizing after irrevocable losses, assuming every other vector good.

    Both the confidence bound and sufficient-event tails increase with the
    good count. Failure of this optimistic completion therefore permits only
    an early futility stop. It cannot justify sizing or an early success.
    """
    if (type(total) is not int or total < 5 or type(known_bad) is not int
            or not 0 <= known_bad <= total):
        raise ValueError("Fixed pilot count and distinct irretrievable vector count required")
    lower = good_probability_lower(total - known_bad, total)
    possible = []
    for count in range(5, 21):
        required = required_good_vectors(count)
        power = 0.0 if required is None else max(0.0, math.nextafter(
            float(binom.sf(required - 1, count, lower)), 0.0))
        if power >= .8:
            possible.append(count)
    return {"pilot_vectors": total, "known_bad_vectors": known_bad,
            "maximum_good_vectors": total - known_bad,
            "optimistic_chosen_n": min(possible) if possible else None,
            "futile": not possible, "certifies_acceptance": False}


def size_joint_vectors(rows, unresolved, grid, *, policy):
    """A single frozen method, not the favorable choice of two pilot analyses.

    Monotonicity of the registered E makes every component reject at .025
    whenever at least k_n vectors exceed c on all components. Fully resolved
    good vectors also imply <=10% unresolved studies per arm. Exact binomial
    tails bound that sufficient joint event. Actual cost vetoes remain separate.
    """
    if policy != JOINT_SIZING_POLICY:
        raise ValueError("Frozen joint-event pilot sizing rule required")
    if (not isinstance(grid, list) or len(grid) < 2 or grid[0] != 0 or grid[-1] != 1
            or any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in grid)
            or any(a >= b for a, b in zip(grid, grid[1:]))):
        raise ValueError("Frozen increasing budget grid required")
    entries = ("V04-T0", "V05")
    if set(rows) != set(entries) or set(unresolved) != set(entries):
        raise ValueError("Both pilot entries required")
    results = {}
    for entry in entries:
        values, flags = rows[entry], unresolved[entry]
        components = rank_components(entry)
        if (not isinstance(values, list) or len(values) < 5 or len(flags) != len(values)
                or any(type(flag) is not bool for flag in flags)):
            raise ValueError("Complete planned pilot vectors and loss flags required")
        magnitudes = [1 - grid[1] if key[-1] == "anytime_win" else 1.0 for key in components]
        for row in values:
            if (not isinstance(row, list) or len(row) != len(components)
                    or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                           or not -1 <= x <= b + 1e-12 for x, b in zip(row, magnitudes))):
                raise ValueError("Invalid retained pilot vector support or component coverage")
        good = sum(not lost and all(min(x, b) >= float(THRESHOLD) for x, b in zip(row, magnitudes))
                   for row, lost in zip(values, flags))
        lower = good_probability_lower(good, len(values))
        frontier = []
        for count in range(5, 21):
            required = required_good_vectors(count)
            power = 0.0 if required is None else max(0.0, math.nextafter(
                float(binom.sf(required - 1, count, lower)), 0.0))
            frontier.append({"n": count, "required_good_vectors": required,
                             "power_lower_conditional_on_resources": power})
        chosen = next((row["n"] for row in frontier if row["power_lower_conditional_on_resources"] >= .8), None)
        results[entry] = {"pilot_vectors": len(values), "good_vectors": good,
                          "good_probability_lower": lower, "chosen_n": chosen, "frontier": frontier}
    return {"kind": "independent_pilot_rank_sizing_v1", "policy": policy, "entries": results,
            "verdict": "SIZED" if all(row["chosen_n"] is not None for row in results.values()) else "INFEASIBLE_UNDER_RULE",
            "confidence": .95, "power_target": .8, "certifies_acceptance": False,
            "assumptions": ["Independent stationary pilot/confirmation vectors from the identical frozen experiment.",
                            "Arbitrary dependence among components, arms and tasks within each vector.",
                            "Separate confirmation and random streams; no outcome reuse.",
                            "Adequate frozen resources; actual cost vetoes remain binding."],
            "scope": "entry_power_with_simultaneous_planning_confidence_conditional_on_resources"}
