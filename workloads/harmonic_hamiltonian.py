"""A learned quadratic Hamiltonian with analytic held-out oscillator data.

This restricted polynomial-feature model isolates architecture and fitting
correctness. It is not a claim about general neural Hamiltonian training.
"""
import numpy as np
from scipy.linalg import expm


def trajectory(initial, times, frequency=1.):
    q, p = initial
    times = np.asarray(times)
    return np.column_stack([q*np.cos(frequency*times)+p/frequency*np.sin(frequency*times),
                            p*np.cos(frequency*times)-frequency*q*np.sin(frequency*times)])


def fit_hamiltonian(basis=("q2", "p2"), ridge=0., frequency=1.):
    """Fit H=(a*q²+2*b*q*p+c*p²)/2 to deterministic training derivatives.

    Quadratic feature subsets form the architecture coordinates. Independent
    initial states/times measure vector-field error and true-energy drift along
    the learned model, so a constant Hamiltonian cannot pass by conserving zero.
    """
    if (not isinstance(basis, (list, tuple)) or not basis or len(set(basis)) != len(basis)
            or not set(basis) <= {"q2", "qp", "p2"}):
        raise ValueError("A nonempty unique subset of q2/qp/p2 is required")
    if (isinstance(ridge, bool) or not np.isfinite(ridge) or ridge < 0
            or isinstance(frequency, bool) or not np.isfinite(frequency) or frequency <= 0):
        raise ValueError("Finite nonnegative ridge and positive frequency required")
    training_initials = ((1., 0.), (0., 1.))
    heldout_initials = ((.3, 1.2), (-.7, .4), (1.1, -.5))
    train_times = np.array([0., .5, 1.])
    heldout_times = np.array([.2, .7, 1.3, 2.1])
    states = np.concatenate([trajectory(x, train_times, frequency) for x in training_initials])
    q, p = states.T
    columns = {"q2": np.column_stack([np.zeros_like(q), -q]),
               "qp": np.column_stack([q, -p]),
               "p2": np.column_stack([p, np.zeros_like(p)])}
    design = np.column_stack([columns[k].reshape(-1) for k in basis])
    target = np.column_stack([p, -frequency**2*q]).reshape(-1)
    coefficients = np.linalg.solve(design.T @ design + ridge*np.eye(len(basis)), design.T @ target)
    values = dict(zip(basis, coefficients))
    a, b, c = values.get("q2", 0.), values.get("qp", 0.), values.get("p2", 0.)
    flow = np.array([[b, c], [-a, -b]])
    heldout = np.concatenate([trajectory(x, heldout_times, frequency) for x in heldout_initials])
    predicted = heldout @ flow.T
    exact = np.column_stack([heldout[:, 1], -frequency**2*heldout[:, 0]])
    learned_paths = np.array([[expm(t*flow) @ initial for t in [0., *heldout_times]]
                             for initial in heldout_initials])
    energies = (frequency**2 * learned_paths[:, :, 0]**2 + learned_paths[:, :, 1]**2)/2
    drift = np.max(np.abs(energies - energies[:, :1]))
    return {"method": "quadratic_feature_hamiltonian_ridge_fit", "target": "harmonic_oscillator",
            "frequency": frequency, "basis": list(basis), "ridge": float(ridge),
            "coefficients": coefficients.tolist(), "prediction_error": float(np.mean((predicted-exact)**2)),
            "true_energy_drift": float(drift), "directions": ["minimize", "minimize"],
            "training_initials": training_initials, "heldout_initials": heldout_initials,
            "training_times": train_times.tolist(), "heldout_times": heldout_times.tolist(),
            "heldout_states": heldout.tolist(), "predicted_derivatives": predicted.tolist(),
            "learned_paths": learned_paths.tolist(), "fitted_parameter_count": len(basis),
            "work": {"training_derivative_rows": int(design.shape[0]), "linear_solves": 1,
                     "heldout_derivative_rows": len(heldout), "matrix_exponentials": 15}}
