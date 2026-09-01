"""
GP + qLogEI searcher via BoTorch.

Survey reference: Ch 4 roadmap-05, ch04-01, ch04-05.
Survey verdict: include, T0, ~8 engineer-days (core build).
Contract: GP surrogate with dimension-scaled priors, qLogEI acquisition.
Validation: V01 (parity with BoTorch reference), V04 (beats log+Sobol floor), V05 (log-warping matters).

Tier 0: continuous knobs only, dimension-scaled lengthscale priors, log-warping.
Tier 1: adds TuRBO trust regions, prior-aware acquisition (πBO).
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    import torch
    import botorch
    from botorch.models import SingleTaskGP
    from botorch.fit import fit_gpytorch_mll
    from botorch.acquisition.logei import qLogExpectedImprovement
    from botorch.optim import optimize_acqf
    from botorch.sampling import SobolQMCNormalSampler
    import gpytorch
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from gpytorch.kernels import MaternKernel, ScaleKernel
    from gpytorch.priors import GammaPrior
    BOTORCH_AVAILABLE = True
except ImportError:
    BOTORCH_AVAILABLE = False

from .space import SearchSpace


class GPqLogEISearcher:
    """
    GP + qLogEI searcher (Ch 4 roadmap-05, ch04-01, ch04-05).

    Survey verdict: include, T0, ~8 engineer-days.
    Contract:
    - SingleTaskGP with Matern-5/2 kernel
    - Dimension-scaled lengthscale priors (ch04-05)
    - qLogEI acquisition (log-transformed for scale stability)
    - Log-warping for scale-sensitive parameters (V05 test)

    Tier 0: continuous knobs only, batch proposals via qLogEI.
    Multi-objective (qLogNEHVI) deferred to Tier 1.
    """

    def __init__(
        self,
        space: SearchSpace,
        seed: int = 0,
        n_fantasies: int = 64,  # qLogEI MC samples
        raw_samples: int = 512,  # Acquisition optimization initial samples
        n_restarts: int = 10,  # Acquisition optimization restarts
    ):
        if not BOTORCH_AVAILABLE:
            raise ImportError("GPqLogEISearcher requires botorch: pip install botorch gpytorch torch")

        self.space = space
        self.seed = seed
        self.n_fantasies = n_fantasies
        self.raw_samples = raw_samples
        self.n_restarts = n_restarts

        # Filter to continuous knobs (Tier 0 limitation)
        self.cont_knobs = [k for k in space.knobs if k.kind == "continuous" and not k.condition]
        if not self.cont_knobs:
            raise ValueError("GPqLogEISearcher: no continuous knobs in space (Tier 0 limitation)")

        self._dim = len(self.cont_knobs)
        self._n_proposed = 0
        self._n_observed = 0

        # Observation buffers (normalized to [0, 1]^d unit cube)
        self._X: list[torch.Tensor] = []  # Configurations
        self._Y: list[torch.Tensor] = []  # Objectives

        # BoTorch expects [0, 1]^d; we store bounds for transform
        self._bounds_low = torch.tensor([k.bounds[0] for k in self.cont_knobs], dtype=torch.float64)
        self._bounds_high = torch.tensor([k.bounds[1] for k in self.cont_knobs], dtype=torch.float64)

        # Track which dimensions use log-warping (V05 test requirement)
        self._log_dims = torch.tensor([k.transform == "log" for k in self.cont_knobs], dtype=torch.bool)

        # GP model and acquisition function (built after first observation)
        self._model = None
        self._acqf = None

        # RNG for initial random sampling
        self._rng = np.random.default_rng(seed)
        torch.manual_seed(seed)

    def _to_unit_cube(self, config: dict[str, Any]) -> torch.Tensor:
        """
        Transform config from original space to [0, 1]^d unit cube.

        Log-warped dimensions: first apply log, then normalize to [0, 1].
        Linear dimensions: normalize directly to [0, 1].
        """
        x = torch.zeros(self._dim, dtype=torch.float64)
        for i, knob in enumerate(self.cont_knobs):
            val = config[knob.name]
            low, high = knob.bounds

            if knob.transform == "log":
                # Log-warp: x_unit = (log(val) - log(low)) / (log(high) - log(low))
                log_low, log_high = np.log(low), np.log(high)
                log_val = np.log(val)
                x[i] = (log_val - log_low) / (log_high - log_low)
            else:
                # Linear: x_unit = (val - low) / (high - low)
                x[i] = (val - low) / (high - low)

        return x

    def _from_unit_cube(self, x_unit: torch.Tensor) -> dict[str, Any]:
        """
        Transform from [0, 1]^d unit cube back to original space.
        """
        config: dict[str, Any] = {}
        for i, knob in enumerate(self.cont_knobs):
            u = x_unit[i].item()
            low, high = knob.bounds

            if knob.transform == "log":
                # Inverse log-warp: val = exp(log(low) + u * (log(high) - log(low)))
                log_low, log_high = np.log(low), np.log(high)
                val = np.exp(log_low + u * (log_high - log_low))
            else:
                # Inverse linear: val = low + u * (high - low)
                val = low + u * (high - low)

            config[knob.name] = float(val)

        return config

    def _build_gp(self) -> None:
        """
        Build GP model with dimension-scaled priors (ch04-05).

        Survey: lengthscale prior scaled by sqrt(d) for robustness across dimensions.
        Prior: Gamma(3.0, 6.0 / sqrt(d)) gives mean ≈ 0.5 * sqrt(d), reasonable for unit cube.
        """
        if len(self._X) == 0:
            return

        X_train = torch.stack(self._X)
        Y_train = torch.stack(self._Y).unsqueeze(-1)  # [n, 1]

        # Dimension-scaled lengthscale prior (ch04-05)
        lengthscale_prior = GammaPrior(3.0, 6.0 / np.sqrt(self._dim))

        # Matern-5/2 kernel with scaled prior
        covar_module = ScaleKernel(
            MaternKernel(
                nu=2.5,
                ard_num_dims=self._dim,
                lengthscale_prior=lengthscale_prior,
            )
        )

        self._model = SingleTaskGP(
            train_X=X_train,
            train_Y=Y_train,
            covar_module=covar_module,
        )

        mll = ExactMarginalLogLikelihood(self._model.likelihood, self._model)
        fit_gpytorch_mll(mll)

    def _build_acqf(self, batch_size: int) -> None:
        """Build qLogEI acquisition function."""
        if self._model is None:
            return

        X_train = torch.stack(self._X)

        # Find best observed value for Expected Improvement
        Y_train = torch.stack(self._Y)
        best_f = Y_train.max().item()

        # qLogEI with MC sampling
        sampler = SobolQMCNormalSampler(sample_shape=torch.Size([self.n_fantasies]), seed=self.seed)

        self._acqf = qLogExpectedImprovement(
            model=self._model,
            best_f=best_f,
            sampler=sampler,
        )

    def propose(self, n: int) -> list[dict[str, Any]]:
        """
        Propose n configurations via GP + qLogEI.

        Bootstrap: If no observations yet, use Sobol initialization.
        Active: Optimize qLogEI acquisition function.
        """
        configs = []

        # Bootstrap phase: no observations yet, use Sobol
        if self._n_observed == 0:
            from scipy.stats import qmc
            sobol = qmc.Sobol(d=self._dim, scramble=True, seed=self.seed)
            points = sobol.random(n)

            for point in points:
                x_unit = torch.tensor(point, dtype=torch.float64)
                config = self._from_unit_cube(x_unit)
                configs.append(config)

            self._n_proposed += n
            return configs

        # Active phase: optimize qLogEI
        self._build_gp()
        self._build_acqf(batch_size=n)

        # BoTorch batch acquisition optimization
        bounds = torch.stack([
            torch.zeros(self._dim, dtype=torch.float64),
            torch.ones(self._dim, dtype=torch.float64),
        ])

        candidates, _ = optimize_acqf(
            acq_function=self._acqf,
            bounds=bounds,
            q=n,  # Batch size
            num_restarts=self.n_restarts,
            raw_samples=self.raw_samples,
        )

        # Convert candidates from [0, 1]^d back to original space
        for i in range(n):
            x_unit = candidates[i]
            config = self._from_unit_cube(x_unit)
            configs.append(config)

        self._n_proposed += n
        return configs

    def observe(self, trial_result: dict[str, Any]) -> None:
        """
        Ingest one trial result.

        Expected trial_result format:
        {
            "config": dict[str, Any],
            "value": float,  # objective value (maximize)
            "fidelity": float | None,
            "cost": float | None,
        }
        """
        config = trial_result["config"]
        value = trial_result["value"]

        # Transform to unit cube and store
        x_unit = self._to_unit_cube(config)
        y = torch.tensor(value, dtype=torch.float64)

        self._X.append(x_unit)
        self._Y.append(y)

        self._n_observed += 1

        # Invalidate cached model (will rebuild on next propose())
        self._model = None
        self._acqf = None

    def state_dict(self) -> dict[str, Any]:
        """Serialize state for crash recovery."""
        return {
            "kind": "gp_qlogei",
            "seed": self.seed,
            "n_proposed": self._n_proposed,
            "n_observed": self._n_observed,
            "X": [x.tolist() for x in self._X],
            "Y": [y.item() for y in self._Y],
            "knob_names": [k.name for k in self.cont_knobs],
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore state after crash."""
        if state.get("kind") != "gp_qlogei":
            raise ValueError(f"GPqLogEISearcher cannot load state of kind {state.get('kind')!r}")

        # Verify knob structure matches
        expected = [k.name for k in self.cont_knobs]
        if state.get("knob_names") != expected:
            raise ValueError(
                f"Searcher state does not match space: state has {state.get('knob_names')}, "
                f"space has {expected}"
            )

        self.seed = state["seed"]
        self._n_proposed = state["n_proposed"]
        self._n_observed = state["n_observed"]

        # Restore observations
        self._X = [torch.tensor(x, dtype=torch.float64) for x in state["X"]]
        self._Y = [torch.tensor(y, dtype=torch.float64) for y in state["Y"]]

        # Model will rebuild on next propose()
        self._model = None
        self._acqf = None

        torch.manual_seed(self.seed)

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare GP capabilities."""
        return {
            "knob_kinds": ["continuous"],  # Tier 0: continuous only
            "conditionals": False,
            "multi_objective": False,  # Tier 1: qLogNEHVI
            "prior": False,  # Tier 1: πBO
            "max_dim": 20,  # Reasonable for standard GP without trust regions
        }
