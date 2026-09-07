"""
hamiltonian_mo workload: multi-objective Hamiltonian network tuning.

Survey reference: Ch 7 (MO methods), Ch 10 (Hamiltonian regime).
Survey verdict: T1, production template (~5d).
Validation: V09 (qLogNEHVI vs scalarization), V10 (drift correlation).

This is the "Hamiltonian networks" regime: physics-informed neural networks
learning conservative dynamics from trajectory data. The workload exposes
prediction error (MSE on held-out trajectories) and drift (energy conservation
violation) as competing objectives.

Tier 1 requirements:
- Two objectives: prediction_error (minimize), drift (minimize)
- Real Hamiltonian network architecture
- Real physics task (pendulum, spring, or double pendulum)
- Multi-fidelity: training epochs
- Drift measurable at intermediate rungs for V10
"""

from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class HamiltonianNet(nn.Module):
    """
    Hamiltonian neural network with symplectic structure.

    Learns H(q, p) such that dq/dt = ∂H/∂p, dp/dt = -∂H/∂q.
    """
    def __init__(self, hidden_sizes: list[int], activation: str = "tanh"):
        super().__init__()

        # Input: (q, p) coordinates
        # Output: scalar Hamiltonian H(q, p)
        layers = []
        in_dim = 2  # (q, p) for 1D system

        for h in hidden_sizes:
            layers.append(nn.Linear(in_dim, h))
            if activation == "tanh":
                layers.append(nn.Tanh())
            elif activation == "relu":
                layers.append(nn.ReLU())
            elif activation == "elu":
                layers.append(nn.ELU())
            else:
                raise ValueError(f"Unknown activation: {activation}")
            in_dim = h

        layers.append(nn.Linear(in_dim, 1))  # Scalar output
        self.net = nn.Sequential(*layers)

    def forward(self, qp: torch.Tensor) -> torch.Tensor:
        """Compute H(q, p)."""
        return self.net(qp)

    def time_derivative(self, qp: torch.Tensor) -> torch.Tensor:
        """
        Compute time derivative using Hamiltonian equations.

        Returns: (dq/dt, dp/dt) = (∂H/∂p, -∂H/∂q)
        """
        qp.requires_grad_(True)
        H = self.forward(qp)

        # Compute gradients
        grad = torch.autograd.grad(
            H.sum(), qp, create_graph=True, allow_unused=False
        )[0]

        # Symplectic structure: dq/dt = ∂H/∂p, dp/dt = -∂H/∂q
        dq_dt = grad[:, 1:2]  # ∂H/∂p
        dp_dt = -grad[:, 0:1]  # -∂H/∂q

        return torch.cat([dq_dt, dp_dt], dim=1)


def generate_pendulum_data(
    n_trajectories: int = 10,
    n_steps: int = 100,
    dt: float = 0.1,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate training data from ideal pendulum dynamics.

    Hamiltonian: H(q, p) = p²/2 - cos(q)
    Equations: dq/dt = p, dp/dt = -sin(q)

    Returns:
        states: (n_trajectories * n_steps, 2) array of (q, p)
        derivatives: (n_trajectories * n_steps, 2) array of (dq/dt, dp/dt)
    """
    rng = np.random.RandomState(seed)

    all_states = []
    all_derivs = []

    for _ in range(n_trajectories):
        # Random initial condition
        q0 = rng.uniform(-np.pi, np.pi)
        p0 = rng.uniform(-2.0, 2.0)

        states = [(q0, p0)]

        # Integrate using RK4
        q, p = q0, p0
        for _ in range(n_steps - 1):
            # RK4 for pendulum
            def derivs(q, p):
                return p, -np.sin(q)

            k1_q, k1_p = derivs(q, p)
            k2_q, k2_p = derivs(q + 0.5*dt*k1_q, p + 0.5*dt*k1_p)
            k3_q, k3_p = derivs(q + 0.5*dt*k2_q, p + 0.5*dt*k2_p)
            k4_q, k4_p = derivs(q + dt*k3_q, p + dt*k3_p)

            q = q + (dt/6) * (k1_q + 2*k2_q + 2*k3_q + k4_q)
            p = p + (dt/6) * (k1_p + 2*k2_p + 2*k3_p + k4_p)

            states.append((q, p))

        # Compute derivatives
        traj_states = np.array(states)
        traj_derivs = np.zeros_like(traj_states)
        traj_derivs[:, 0] = traj_states[:, 1]  # dq/dt = p
        traj_derivs[:, 1] = -np.sin(traj_states[:, 0])  # dp/dt = -sin(q)

        all_states.append(traj_states)
        all_derivs.append(traj_derivs)

    states = np.concatenate(all_states, axis=0)
    derivatives = np.concatenate(all_derivs, axis=0)

    return states, derivatives


def compute_energy_drift(
    model: HamiltonianNet,
    states: np.ndarray,
    n_traj: int,
    steps_per_traj: int,
) -> float:
    """
    Measure energy conservation violation along test trajectories.

    Ideal Hamiltonian systems conserve energy. Drift is the standard deviation
    of H(q(t), p(t)) along each trajectory, averaged over trajectories.
    """
    model.eval()

    with torch.no_grad():
        states_t = torch.from_numpy(states).float()
        energies = model.forward(states_t).squeeze().numpy()

    # Reshape to (n_traj, steps_per_traj)
    energies = energies.reshape(n_traj, steps_per_traj)

    # Drift = std along each trajectory, then average
    drifts = energies.std(axis=1)
    mean_drift = drifts.mean()

    return float(mean_drift)


def hamiltonian_mo(
    config: dict[str, Any],
    fidelity: float = 1.0,
    seed: int = 0,
) -> dict[str, Any]:
    """
    Hamiltonian multi-objective workload.

    Args:
        config: Hyperparameter configuration
        fidelity: Training budget (fraction of max_epochs)
        seed: Random seed

    Returns:
        dict with keys:
            - prediction_error: MSE on held-out trajectories (minimize)
            - drift: Energy conservation violation (minimize)
            - cost: Wall-clock seconds

    Config schema:
        learning_rate: float in [1e-5, 1e-2], log-scale
        batch_size: int in [16, 256], ordinal
        hidden_sizes: list[int], e.g. [32, 32] or [64, 64, 64]
        activation: str in ["tanh", "relu", "elu"]
        weight_decay: float in [0.0, 1e-2], log-scale
        optimizer: str in ["adam", "sgd", "rmsprop"]
    """
    if not TORCH_AVAILABLE:
        raise ImportError("hamiltonian_mo requires torch: pip install torch")

    # Validate config
    required_keys = [
        "learning_rate", "batch_size", "hidden_sizes",
        "activation", "weight_decay", "optimizer"
    ]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"hamiltonian_mo: missing required config key: {key}")

    # Extract config
    lr = config["learning_rate"]
    batch_size = config["batch_size"]
    hidden_sizes = config["hidden_sizes"]
    activation = config["activation"]
    weight_decay = config["weight_decay"]
    optimizer_name = config["optimizer"]

    # Fidelity
    max_epochs = 100
    n_epochs = max(1, int(fidelity * max_epochs))

    # Generate data
    start_time = time.time()

    train_states, train_derivs = generate_pendulum_data(
        n_trajectories=20, n_steps=100, seed=seed
    )
    test_states, test_derivs = generate_pendulum_data(
        n_trajectories=5, n_steps=100, seed=seed + 1000
    )

    # Convert to torch
    train_states_t = torch.from_numpy(train_states).float()
    train_derivs_t = torch.from_numpy(train_derivs).float()
    test_states_t = torch.from_numpy(test_states).float()
    test_derivs_t = torch.from_numpy(test_derivs).float()

    # Build model
    torch.manual_seed(seed)
    model = HamiltonianNet(hidden_sizes, activation)

    # Build optimizer
    if optimizer_name == "adam":
        opt = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    elif optimizer_name == "sgd":
        opt = optim.SGD(model.parameters(), lr=lr, weight_decay=weight_decay, momentum=0.9)
    elif optimizer_name == "rmsprop":
        opt = optim.RMSprop(model.parameters(), lr=lr, weight_decay=weight_decay)
    else:
        raise ValueError(f"Unknown optimizer: {optimizer_name}")

    # Training loop
    n_train = len(train_states_t)
    indices = np.arange(n_train)

    for epoch in range(n_epochs):
        model.train()
        np.random.RandomState(seed + epoch).shuffle(indices)

        for i in range(0, n_train, batch_size):
            batch_idx = indices[i:i+batch_size]
            batch_states = train_states_t[batch_idx]
            batch_derivs = train_derivs_t[batch_idx]

            # Compute predicted derivatives
            pred_derivs = model.time_derivative(batch_states)

            # MSE loss
            loss = ((pred_derivs - batch_derivs) ** 2).mean()

            opt.zero_grad()
            loss.backward()
            opt.step()

    # Evaluate prediction error on test set
    model.eval()
    test_pred_derivs = model.time_derivative(test_states_t)
    prediction_error = ((test_pred_derivs - test_derivs_t) ** 2).mean().item()

    # Evaluate drift
    drift = compute_energy_drift(model, test_states, n_traj=5, steps_per_traj=100)

    cost = time.time() - start_time

    return {
        "prediction_error": prediction_error,
        "drift": drift,
        "cost": cost,
    }
