"""Independent rational references for finite numerical tuning workloads.

No HPO method is evaluated here. These calculations do not certify current
later-tier algorithms or replace their prospective acceptance contracts.
"""
from fractions import Fraction as Q
from itertools import combinations


def solve(matrix, vector):
    rows = [list(row)+[value] for row, value in zip(matrix, vector)]
    n = len(rows)
    for col in range(n):
        pivot = next(i for i in range(col, n) if rows[i][col])
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [value/divisor for value in rows[col]]
        for i in range(n):
            if i != col:
                multiplier = rows[i][col]
                rows[i] = [a-multiplier*b for a, b in zip(rows[i], rows[col])]
    return [row[-1] for row in rows]


KNOTS = [Q(i, 8) for i in range(1, 8)]
PARTITION = [Q(0), *KNOTS, Q(1)]


def piece(feature, x):
    if feature == "constant":
        return Q(1), Q(0)
    if feature == "linear":
        return Q(0), Q(1)
    return (-feature, Q(1)) if x > feature else (Q(0), Q(0))


def inner(left, right):
    value = Q(0)
    for lo, hi in zip(PARTITION, PARTITION[1:]):
        a, b = piece(left, (lo+hi)/2)
        c, d = piece(right, (lo+hi)/2)
        value += a*c*(hi-lo)+(a*d+b*c)*(hi**2-lo**2)/2+b*d*(hi**3-lo**3)/3
    return value


def spline():
    true = [(Q(1, 4), Q(1)), (Q(1, 2), Q(-2)), (Q(3, 4), Q(1))]
    norm = sum(a*b*inner(x, y) for x, a in true for y, b in true)
    rows = []
    for width in range(8):
        for knots in combinations(KNOTS, width):
            features = ["constant", "linear", *knots]
            gram = [[inner(a, b) for b in features] for a in features]
            target = [sum(coefficient*inner(a, knot) for knot, coefficient in true)
                      for a in features]
            weights = solve(gram, target)
            error = norm-sum(a*b for a, b in zip(weights, target))
            assert error >= 0
            assert (error == 0) == {Q(1, 4), Q(1, 2), Q(3, 4)}.issubset(knots)
            # Verify the normal equations exactly after independently retaining
            # the fitted weights. These are restricted output fits, not SGD.
            assert [sum(a*b for a, b in zip(row, weights)) for row in gram] == target
            rows.append({"knots": list(map(str, knots)), "width": width,
                         "integrated_error": str(error), "weights": list(map(str, weights))})
    frontier = []
    for width in range(8):
        candidates = [r for r in rows if r["width"] == width]
        chosen = min(candidates, key=lambda r: Q(r["integrated_error"]))
        frontier.append({"width": width, "error": chosen["integrated_error"], "knots": chosen["knots"]})
    return {"architecture_count": len(rows), "minimum_exact_width": 3,
            "frontier": frontier, "architectures": rows}


def fidelity():
    risk = lambda eta, t: Q(1, 100)*(1-eta)**(2*t)+(1-3*eta)**(2*t)
    a, b = Q(1, 4), Q(9, 20)
    values = [{"iterations": t, "eta_1_4_error": str(risk(a, t)),
               "eta_9_20_error": str(risk(b, t))} for t in [1, 2, 4, 8]]
    assert risk(a, 1) < risk(b, 1) and risk(a, 8) > risk(b, 8)
    domain = [Q(i, 40) for i in range(1, 26)]
    optimum = min(domain, key=lambda eta: risk(eta, 8))
    return {"hessian_eigenvalues": [1, 3], "initial_error_squared": ["1/100", "1"],
            "early_rank_reversal": values, "finite_eta_domain": list(map(str, domain)),
            "finite_T8_optimum": str(optimum), "finite_T8_minimum": str(risk(optimum, 8)),
            "global_continuous_optimum_claimed": False}


def hmc():
    rows = []
    for c in [Q(-99, 100), Q(-1, 2), Q(0), Q(1, 2), Q(99, 100)]:
        mean = (1+c)/(1-c)
        square = (1+c*c)/(1-c*c)
        score = max(mean, square)
        assert score >= 1 and (score == 1) == (c == 0)
        rows.append({"cos_tau": str(c), "mean_iact": str(mean), "square_iact": str(square),
                     "worst_iact": str(score)})
    return {"model": "exact Gaussian Hamiltonian flow with fresh independent momentum",
            "analytic_optimum_tau": "pi/2 in (0, pi)", "minimum_worst_iact": "1",
            "cases": rows, "finite_leapfrog_or_learned_transport_claimed": False}

