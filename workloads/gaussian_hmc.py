"""Gaussian leapfrog and Metropolis operations, with explicit target identity."""
import math
import hashlib
import json

import numpy as np


def finite(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Finite real input required")
    number = float(value)
    if not math.isfinite(number) or positive and number <= 0:
        raise ValueError("Nonfinite or nonpositive input")
    return number


def leapfrog(q, p, step_size, steps, frequency=1.0):
    q, p = finite(q), finite(p)
    step_size, frequency = finite(step_size, positive=True), finite(frequency, positive=True)
    if type(steps) is not int or not 1 <= steps <= 256:
        raise ValueError("Trajectory length must be an integer in [1,256]")
    omega2 = frequency * frequency
    initial_energy = .5 * (omega2 * q*q + p*p)
    for _ in range(steps):
        p -= .5 * step_size * omega2 * q
        q += step_size * p
        p -= .5 * step_size * omega2 * q
    final_energy = .5 * (omega2 * q*q + p*p)
    if not all(math.isfinite(v) for v in (q, p, initial_energy, final_energy)):
        raise ValueError("Trajectory overflow")
    delta = final_energy - initial_energy
    probability = 1.0 if delta <= 0 else math.exp(-delta)
    return {"q": q, "p": p, "delta_energy": delta, "acceptance_probability": probability}


def metropolis(q, p, step_size, steps, frequency, uniform):
    uniform = finite(uniform)
    if not 0 < uniform < 1:
        raise ValueError("Open-unit-interval uniform required")
    row = leapfrog(q, p, step_size, steps, frequency)
    accepted = math.log(uniform) < min(0.0, -row["delta_energy"])
    return {**row, "accepted": accepted,
            "next_q": row["q"] if accepted else float(q),
            "next_p": -row["p"] if accepted else float(p)}


def proposal_matrix(step_size, steps, frequency):
    first = leapfrog(1.0, 0.0, step_size, steps, frequency)
    second = leapfrog(0.0, 1.0, step_size, steps, frequency)
    return [[first["q"], second["q"]], [first["p"], second["p"]]]


def stationary_mean_acceptance(step_size, steps, frequency):
    """For standard Gaussian momentum and q~N(0,frequency**-2)."""
    import numpy as np
    matrix = proposal_matrix(step_size, steps, frequency)
    whitened = np.array([[matrix[0][0], frequency*matrix[0][1]],
                        [matrix[1][0]/frequency, matrix[1][1]]])
    singular = float(np.linalg.svd(whitened, compute_uv=False)[0])
    return 4.0 / math.pi * math.atan(1.0 / max(1.0, singular))


def chain_diagnostics(chains):
    """Report each marginal's bulk/tail ESS and rank/folded split R-hat."""
    from workloads.sampler_neutra import _ess, _rank_normalize, _rhat, _split_chains
    split = _split_chains(chains)
    results = []
    for dimension in range(split.shape[2]):
        x = split[:, :, dimension]
        if np.any(x.var(axis=1) == 0):
            row = {"bulk_ess": 0., "tail_ess": 0., "rhat": float("inf")}
        else:
            rank = _rank_normalize(x)
            lo, hi = np.quantile(x, [.05, .95])
            row = {"bulk_ess": _ess(rank),
                   "tail_ess": min(_ess((x <= lo).astype(float)), _ess((x >= hi).astype(float))),
                   "rhat": max(_rhat(rank), _rhat(_rank_normalize(np.abs(x - np.median(x)))))}
        results.append(row)
    return {"marginals": results, "bulk_ess": min(r["bulk_ess"] for r in results),
            "tail_ess": min(r["tail_ess"] for r in results), "rhat": max(r["rhat"] for r in results)}


def correctness_veto(diagnostics, divergences, *, max_rhat=1.01, min_ess=400):
    """Apply the registered absolute vetoes before any efficiency ranking.

    Passing these vetoes alone supplies no SBC, posterior agreement, or V13 PASS.
    """
    max_rhat, min_ess = finite(max_rhat, positive=True), finite(min_ess, positive=True)
    if type(divergences) is not int or divergences < 0:
        raise ValueError("A nonnegative divergence count is required")
    reasons = []
    if divergences:
        reasons.append("divergent_transition")
    if not math.isfinite(diagnostics["rhat"]) or diagnostics["rhat"] > max_rhat:
        reasons.append("rhat")
    for key in ["bulk_ess", "tail_ess"]:
        if not math.isfinite(diagnostics[key]) or diagnostics[key] < min_ess:
            reasons.append(key)
    return {"eligible_for_calibration": not reasons, "veto_reasons": reasons,
            "scientific_acceptance": False}


def _binding(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def sample_gaussian(*, step_size, steps, frequency=1., draws=32, warmup=0,
                    initial_positions=(-3., -1., 1., 3.), seed=0, checkpoint=None):
    """Run bounded ordinary HMC; retain all transitions and incremental work.

    ``draws`` is the total desired retained fidelity. Warmup is charged and its
    divergences are retained. Resume never repeats warmup or committed draws.
    The target is N(0,frequency**-2); no learned transport or NUTS is implied.
    """
    step_size, frequency = finite(step_size, positive=True), finite(frequency, positive=True)
    if (type(steps) is not int or not 1 <= steps <= 256
            or type(draws) is not int or not 4 <= draws <= 8192
            or type(warmup) is not int or not 0 <= warmup <= 8192
            or type(seed) is not int or not 0 <= seed < 2**32):
        raise ValueError("Invalid bounded sampling configuration")
    initial = [finite(x) for x in initial_positions]
    if not 2 <= len(initial) <= 8:
        raise ValueError("Sampling requires two to eight initial positions")
    identity = {"schema": "gaussian_hmc_v1", "target": "centered_univariate_gaussian",
                "method": "leapfrog_metropolis_full_momentum_refresh", "frequency": frequency,
                "step_size": step_size, "steps": steps, "warmup": warmup,
                "initial_positions": initial, "seed": seed}
    q, rng = np.array(initial), np.random.RandomState(seed)
    trace, completed = [], 0
    if checkpoint is not None:
        body = {k: v for k, v in checkpoint.items() if k != "binding"}
        if checkpoint.get("binding") != _binding(body) or checkpoint.get("identity") != identity:
            raise ValueError("Sampler checkpoint identity/binding differs")
        completed = checkpoint["completed_draws"]
        if type(completed) is not int or not 0 <= completed <= draws:
            raise ValueError("Sampler checkpoint fidelity differs")
        q = np.array([finite(x) for x in checkpoint["positions"]])
        trace = json.loads(json.dumps(checkpoint["trace"]))
        if (q.shape != (len(initial),) or len(trace) != warmup + completed
                or checkpoint["gradient_evaluations"] != len(trace) * len(initial) * 2 * steps):
            raise ValueError("Sampler checkpoint work/trace differs")
        for index, row in enumerate(trace):
            if (row["phase"] != ("warmup" if index < warmup else "retained")
                    or len(row["transitions"]) != len(initial)):
                raise ValueError("Sampler checkpoint transition identity differs")
        if trace and [t["next_q"] for t in trace[-1]["transitions"]] != q.tolist():
            raise ValueError("Sampler checkpoint state differs from its last transition")
        state = checkpoint["rng_state"]
        rng.set_state((state[0], np.array(state[1], dtype=np.uint32), *state[2:]))
    start_length = len(trace)
    target_length = warmup + draws
    for index in range(start_length, target_length):
        transitions = []
        for chain in range(len(initial)):
            p, uniform = float(rng.normal()), float(rng.uniform(np.nextafter(0., 1.), 1.))
            try:
                row = metropolis(float(q[chain]), p, step_size, steps, frequency, uniform)
                row["diverged"] = abs(row["delta_energy"]) > 1000
                if row["diverged"]:
                    row.update(accepted=False, next_q=float(q[chain]), next_p=p)
            except (ValueError, OverflowError, FloatingPointError):
                row = {"accepted": False, "next_q": float(q[chain]), "next_p": p,
                       "diverged": True, "delta_energy": None, "acceptance_probability": 0.}
            transitions.append(row)
            q[chain] = row["next_q"]
        trace.append({"phase": "warmup" if index < warmup else "retained", "transitions": transitions})
    retained = np.array([[t["next_q"] for t in row["transitions"]] for row in trace[warmup:]]).T[:, :, None]
    diagnostics = chain_diagnostics(retained)
    divergences = sum(t["diverged"] for row in trace for t in row["transitions"])
    accepted = sum(t["accepted"] for row in trace for t in row["transitions"])
    state = rng.get_state()
    work_per_iteration = len(initial) * 2 * steps
    body = {"identity": identity, "completed_draws": draws, "positions": q.tolist(), "trace": trace,
            "rng_state": [state[0], state[1].tolist(), *state[2:]],
            "gradient_evaluations": len(trace) * work_per_iteration}
    return {"identity": identity, "chains": retained.tolist(), "diagnostics": diagnostics,
            "divergences": int(divergences), "accepted": int(accepted),
            "veto": correctness_veto(diagnostics, int(divergences)),
            "incremental_gradient_evaluations": (len(trace) - start_length) * work_per_iteration,
            "gradient_evaluations": body["gradient_evaluations"],
            "checkpoint": {**body, "binding": _binding(body)}}
