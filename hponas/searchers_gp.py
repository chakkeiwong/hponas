"""
⚠️ OLD CODE - DO NOT USE IN NEW IMPLEMENTATIONS ⚠️
This file is LEGACY code from pre-recovery implementation.
- Used only by validation scripts (v11, v16)
- Contains specification violations (see TRACEABILITY_MATRIX_v1.md)
- New implementations should use hponas/searchers/gp_searcher.py

GP + qLogEI searcher via BoTorch.

Survey reference: Ch 4 roadmap-05, ch04-01, ch04-05.
Survey verdict: include, T0, ~8 engineer-days (core build).
Contract: GP surrogate with dimension-scaled priors, qLogEI acquisition.
Validation: V01 (parity with BoTorch reference), V04 (beats log+Sobol floor), V05 (log-warping matters).

Tier 0: continuous knobs only, dimension-scaled lengthscale priors, log-warping.
Tier 1: adds TuRBO trust regions, prior-aware acquisition (πBO).
"""

from __future__ import annotations

from typing import Any, Optional

import hashlib
import inspect
import marshal
from pathlib import Path
import cloudpickle
import numpy as np

try:
    import torch
    import botorch
    from botorch.models import SingleTaskGP
    from botorch.fit import fit_gpytorch_mll
    from botorch.acquisition.logei import qLogExpectedImprovement
    from botorch.acquisition import AcquisitionFunction
    from botorch.optim import optimize_acqf
    from botorch.sampling import SobolQMCNormalSampler
    import gpytorch
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from gpytorch.kernels import MaternKernel, ScaleKernel
    from gpytorch.priors import GammaPrior
    BOTORCH_AVAILABLE = True
except ImportError:
    BOTORCH_AVAILABLE = False

from .priors import MIN_DENSITY, ensure_guarded
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
        prior_beta: float = 2.0,  # πBO: prior decay rate (Tier 1)
        prior_fn: Optional[callable] = None,  # πBO: user prior π(x) (Tier 1)
    ):
        if not BOTORCH_AVAILABLE:
            raise ImportError("GPqLogEISearcher requires botorch: pip install botorch gpytorch torch")

        self._validate_controls(seed, n_fantasies, raw_samples, n_restarts, prior_beta)
        if not space.knobs or any(
            k.kind != "continuous" or k.condition or k.transform not in {"none", "log"}
            for k in space.knobs
        ):
            raise ValueError("GPqLogEISearcher requires unconditional continuous knobs with none/log transforms")
        self.space = space
        self.seed = seed
        self.n_fantasies = n_fantasies
        self.raw_samples = raw_samples
        self.n_restarts = n_restarts
        self.prior_beta = float(prior_beta)
        # Guard user prior at entry to guarantee nonzero density
        self.prior_fn = ensure_guarded(prior_fn, space)

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
        self._torch_rng_state = torch.Generator().manual_seed(seed).get_state()

    @staticmethod
    def _validate_controls(seed, n_fantasies, raw_samples, n_restarts, prior_beta):
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        for name, value in (("n_fantasies", n_fantasies), ("raw_samples", raw_samples),
                            ("n_restarts", n_restarts)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(prior_beta, bool) or not np.isscalar(prior_beta):
            raise ValueError("prior_beta must be finite and nonnegative")
        try:
            valid_beta = np.isfinite(prior_beta) and prior_beta >= 0
        except TypeError:
            valid_beta = False
        if not valid_beta:
            raise ValueError("prior_beta must be finite and nonnegative")

    def _prior_identity(self):
        # Compare serialized callables; never execute a pickle from a checkpoint.
        # Recovery requires the same prior recipe in the same Python environment.
        identity = hashlib.sha256(cloudpickle.dumps(self.prior_fn))
        raw = getattr(self.prior_fn, "user_prior", self.prior_fn)
        # Cloudpickle can encode importable functions by module/name alone. Bind
        # their actual code/source too, so changing that function cannot pass as
        # an unchanged prior merely by keeping its name.
        function = raw if inspect.isfunction(raw) else getattr(raw, "__call__", None)
        if getattr(function, "__code__", None) is not None:
            identity.update(marshal.dumps(function.__code__))
            source = inspect.getsourcefile(function)
            if source and Path(source).is_file():
                identity.update(Path(source).read_bytes())
        return identity.hexdigest()

    @staticmethod
    def _versions():
        import platform
        import scipy

        return {"python": platform.python_version(), "torch": str(torch.__version__),
                "botorch": botorch.__version__, "gpytorch": gpytorch.__version__,
                "numpy": np.__version__, "scipy": scipy.__version__,
                "cloudpickle": cloudpickle.__version__}

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

            if u == 0.0:
                val = low
            elif u == 1.0:
                val = high
            elif knob.transform == "log":
                # Inverse log-warp: val = exp(log(low) + u * (log(high) - log(low)))
                log_low, log_high = np.log(low), np.log(high)
                val = np.exp(log_low + u * (log_high - log_low))
            else:
                # Inverse linear: val = low + u * (high - low)
                val = low + u * (high - low)

            # Floating inverse transforms can round an exact endpoint outside
            # its declared interval (for example exp(log(.1)) > .1).
            config[knob.name] = float(np.clip(val, low, high))

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
        """
        Build qLogEI acquisition function, optionally with πBO prior weighting.

        Tier 1: If prior_fn is provided, wrap qLogEI with prior-weighted acquisition:
        α^π(x) = α(x) · π(x)^(β/n), where n is number of observations.
        """
        if self._model is None:
            return

        X_train = torch.stack(self._X)

        # Find best observed value for Expected Improvement
        Y_train = torch.stack(self._Y)
        best_f = Y_train.max().item()

        # qLogEI with MC sampling
        sampler = SobolQMCNormalSampler(sample_shape=torch.Size([self.n_fantasies]), seed=self.seed)

        base_acqf = qLogExpectedImprovement(
            model=self._model,
            best_f=best_f,
            sampler=sampler,
        )

        # Tier 1: πBO prior weighting if prior_fn provided
        if self.prior_fn is not None:
            self._acqf = PriorWeightedAcquisition(
                base_acqf=base_acqf,
                prior_fn=self.prior_fn,
                n_observed=self._n_observed,
                beta=self.prior_beta,
                bounds_low=self._bounds_low,
                bounds_high=self._bounds_high,
                cont_knobs=self.cont_knobs,
            )
        else:
            self._acqf = base_acqf

    def propose(self, n: int) -> list[dict[str, Any]]:
        """Propose configurations using an isolated, checkpointed CPU RNG stream."""
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError("n must be a nonnegative integer")
        if n == 0:
            return []
        # Fitting and acquisition initialization can both consume torch randomness.
        # Preserve the caller's stream and advance only this searcher's stream.
        with torch.random.fork_rng(devices=[]):
            torch.set_rng_state(self._torch_rng_state)
            configs = self._propose(n)
            self._torch_rng_state = torch.get_rng_state().clone()
        return configs

    def log_expected_improvement(self, configs):
        """Score a finite q=1 candidate pool on this searcher's own RNG stream.

        An empty objective history uses a constant bootstrap score. Fit or
        acquisition failures propagate; they cannot become a cost-only search.
        """
        if not isinstance(configs, list) or not configs:
            raise ValueError('A nonempty candidate pool is required')
        points = torch.stack([self._to_unit_cube(c) for c in configs]).double().unsqueeze(1)
        if not self._X:
            return np.zeros(len(configs), dtype=float)
        with torch.random.fork_rng(devices=[]):
            torch.set_rng_state(self._torch_rng_state)
            self._build_gp()
            self._build_acqf(batch_size=1)
            with torch.no_grad():
                values = self._acqf(points).reshape(-1).detach().cpu().numpy()
            if values.shape != (len(configs),) or np.isnan(values).any() or np.isposinf(values).any():
                raise ValueError('Invalid log expected improvement values')
            self._torch_rng_state = torch.get_rng_state().clone()
        return values

    def validate_observations(self, rows):
        """Cross-check a wrapping searcher's objective ledger after recovery."""
        if len(rows) != self._n_observed:
            raise ValueError('GP objective ledger length differs')
        for row, x, y in zip(rows, self._X, self._Y):
            if not torch.equal(self._to_unit_cube(row['config']), x) or row['value'] != y.item():
                raise ValueError('GP objective ledger differs')

    def _propose(self, n: int) -> list[dict[str, Any]]:
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
            if self._n_proposed:
                sobol.fast_forward(self._n_proposed)
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
        self.space.validate_config(config)
        if isinstance(value, bool) or not np.isscalar(value):
            raise ValueError("Observation value must be a finite scalar")
        try:
            finite = np.isfinite(value)
        except TypeError:
            finite = False
        if not finite:
            raise ValueError("Observation value must be a finite scalar")

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
            "schema_version": 2,
            "seed": self.seed,
            "n_proposed": self._n_proposed,
            "n_observed": self._n_observed,
            "X": [x.tolist() for x in self._X],
            "Y": [y.item() for y in self._Y],
            "knob_names": [k.name for k in self.cont_knobs],
            "space": self.space.to_dict(),
            "options": {"n_fantasies": self.n_fantasies, "raw_samples": self.raw_samples,
                        "n_restarts": self.n_restarts, "prior_beta": self.prior_beta},
            "prior_identity": self._prior_identity(),
            "versions": self._versions(),
            "torch_rng_state": self._torch_rng_state.tolist(),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Validate the complete recipe before replacing live state.

        Old snapshots omit the RNG/space/prior recipe and require explicit migration.
        Arbitrary prior callables must be reconstructed by the caller, not unpickled
        from checkpoint data. No cross-version reproducibility is claimed.
        """
        if state.get("kind") != "gp_qlogei":
            raise ValueError(f"GPqLogEISearcher cannot load state of kind {state.get('kind')!r}")
        if state.get("schema_version") != 2:
            raise ValueError("Incomplete legacy GP checkpoint; explicit migration required")
        if (state.get("space") != self.space.to_dict()
                or state.get("knob_names") != [k.name for k in self.cont_knobs]):
            raise ValueError("Searcher state does not match space")
        if state.get("prior_identity") != self._prior_identity():
            raise ValueError("Checkpoint prior recipe differs")
        if state.get("versions") != self._versions():
            raise ValueError("Checkpoint dependency versions differ")
        try:
            options = state["options"]
            expected_options = {"n_fantasies", "raw_samples", "n_restarts", "prior_beta"}
            if set(options) != expected_options:
                raise ValueError("Incomplete acquisition options")
            self._validate_controls(state["seed"], **options)
            for key in ("n_observed", "n_proposed"):
                if type(state[key]) is not int or state[key] < 0:
                    raise ValueError("Invalid checkpoint counts")
            observed = state["n_observed"]
            if len(state["X"]) != observed or len(state["Y"]) != observed:
                raise ValueError("Checkpoint observation counts differ")
            xs = [torch.tensor(x, dtype=torch.float64) for x in state["X"]]
            ys = [torch.tensor(y, dtype=torch.float64) for y in state["Y"]]
            if any(x.shape != (self._dim,) or not torch.isfinite(x).all()
                   or (x < 0).any() or (x > 1).any() for x in xs):
                raise ValueError("Invalid checkpoint coordinates")
            if any(y.ndim != 0 or not torch.isfinite(y) for y in ys):
                raise ValueError("Invalid checkpoint objectives")
            values = state["torch_rng_state"]
            if not isinstance(values, list) or not values or any(
                type(v) is not int or not 0 <= v <= 255 for v in values
            ):
                raise ValueError("Invalid checkpoint RNG state")
            rng = torch.tensor(values, dtype=torch.uint8)
            torch.Generator().set_state(rng)  # Validate without touching global state.
        except (KeyError, TypeError, RuntimeError) as exc:
            raise ValueError("Invalid GP checkpoint") from exc
        self.seed = state["seed"]
        self._n_proposed, self._n_observed = state["n_proposed"], observed
        self._X, self._Y, self._torch_rng_state = xs, ys, rng
        for key, value in options.items():
            setattr(self, key, value)
        self._model = None
        self._acqf = None

    @property
    def support(self):
        from hponas.capabilities import SearcherCapabilities
        return SearcherCapabilities(('continuous',), max_dimensions=20,
                                    prior='density_function')

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare GP capabilities."""
        return self.support.report()


# The public prior API accepts Python/scipy callables, which do not carry a torch
# graph. Supply the log-density derivative numerically while retaining the exact
# autograd derivative of the (much more expensive) GP acquisition.
class _LogPrior(torch.autograd.Function):
    @staticmethod
    def forward(ctx, X, evaluate):
        ctx.save_for_backward(X)
        ctx.evaluate = evaluate
        return evaluate(X)

    @staticmethod
    @torch.autograd.function.once_differentiable
    def backward(ctx, grad_output):
        (X,) = ctx.saved_tensors
        step = torch.finfo(X.dtype).eps ** (1 / 3)
        gradient = torch.empty_like(X)
        for j in range(X.shape[-1]):
            lower, upper = X.clone(), X.clone()
            lower[..., j] = (X[..., j] - step).clamp(min=0.0)
            upper[..., j] = (X[..., j] + step).clamp(max=1.0)
            # At the box boundary this becomes a one-sided difference. Priors
            # are never evaluated outside the declared search space.
            width = upper[..., j] - lower[..., j]
            gradient[..., j] = (ctx.evaluate(upper) - ctx.evaluate(lower)) / width
        return grad_output.unsqueeze(-1) * gradient, None


# Tier 1: πBO prior-weighted acquisition
class PriorWeightedAcquisition(AcquisitionFunction):
    """
    πBO: Prior-weighted acquisition function.

    Survey: Ch 8 roadmap-10, ch08-01.
    Formula: α^π(x) = α(x) · π(x)^(β/n)

    The prior multiplier π(x)^(β/n) decays as n (observations) grows:
    - Early in optimization (small n), large exponent β/n steers toward prior
    - Late in optimization (large n), exponent ~0 and data dominates
    - Wrong priors are forgotten rather than obeyed indefinitely

    Args:
        base_acqf: Underlying acquisition function (e.g. qLogEI)
        prior_fn: User prior density π(x), takes dict config → float
        n_observed: Number of observations so far
        beta: Decay rate (controls how long prior matters)
        bounds_low: Lower bounds for denormalization
        bounds_high: Upper bounds for denormalization
        cont_knobs: List of continuous knobs for config reconstruction
    """

    def __init__(
        self,
        base_acqf: AcquisitionFunction,
        prior_fn: callable,
        n_observed: int,
        beta: float,
        bounds_low: torch.Tensor,
        bounds_high: torch.Tensor,
        cont_knobs: list,
    ):
        super().__init__(model=base_acqf.model)
        self.base_acqf = base_acqf
        self.prior_fn = prior_fn
        self.n_observed = n_observed
        self.beta = beta
        self.bounds_low = bounds_low
        self.bounds_high = bounds_high
        self.cont_knobs = cont_knobs

        # Compute exponent once (constant for this acquisition build)
        self.prior_exponent = beta / max(n_observed, 1)  # Avoid division by zero

    def _log_density(self, X: torch.Tensor) -> torch.Tensor:
        """Evaluate scalar Python priors in the original knob coordinates."""
        log_priors = []
        lows, highs = self.bounds_low.tolist(), self.bounds_high.tolist()
        for point in X.detach().cpu().reshape(-1, X.shape[-1]).tolist():
            config = {}
            for u, knob, low, high in zip(point, self.cont_knobs, lows, highs):
                if knob.transform == "log":
                    val = np.exp(np.log(low) + u * np.log(high / low))
                else:
                    val = low + u * (high - low)
                config[knob.name] = float(val)
            prior_val = max(float(self.prior_fn(config)), MIN_DENSITY)
            log_priors.append(np.log(prior_val))
        return X.new_tensor(log_priors).reshape(X.shape[:-1])

    def forward(self, X: torch.Tensor) -> torch.Tensor:
        """
        Evaluate prior-weighted acquisition at candidate points X.

        Args:
            X: (batch_size, q, dim) or (batch_size, dim) tensor in [0, 1]^d normalized space

        Returns:
            Tensor matching `base_acqf(X)`'s shape (one value per t-batch element).

        Implementation notes:
            1. qLogEI returns log-transformed expected improvement, which can be
               negative when EI < 1. Multiplicative weighting π(x)^(β/n) * qLogEI(x)
               inverts preference in the negative regime: a high prior makes a negative
               value more negative (worse), a low prior makes it less negative (better).
               Weighting is therefore applied additively in log-space:

                 qLogEI_weighted(x) = qLogEI(x) + (β/n) * log π(x)

               which is the log of the intended π(x)^(β/n) * EI(x) and preserves the
               intended preference at every sign of qLogEI.

            2. For q > 1 the base acquisition scores the q-set jointly, returning one
               value per t-batch element, while the prior is per point. The q per-point
               log-priors are averaged so the prior term keeps a fixed scale relative to
               the base acquisition as q varies (a sum would grow with q and let the
               prior swamp the acquisition for large batches).

            3. Python prior callables use bounded finite differences for their
               first derivatives. The base acquisition retains its analytical
               gradient. As with other local optimizers, discontinuous priors
               can have flat regions; raw restart samples also use prior values.
        """
        # Base acquisition values (log-scale), shape (batch_size,) for (batch_size, q, dim) input
        base_values = self.base_acqf(X)

        log_priors = _LogPrior.apply(X, self._log_density).to(base_values)

        # Average the per-point log-priors over q, then scale by the decayed exponent
        if X.ndim >= 3:
            log_prior_term = log_priors.mean(dim=-1)
        else:
            log_prior_term = log_priors
        log_prior_term = self.prior_exponent * log_prior_term

        # Additive in log-space: log(π(x)^(β/n) * EI(x)) = qLogEI(x) + (β/n) * log π(x)
        if base_values.ndim == 0:
            return base_values + log_prior_term.reshape(())
        return base_values + log_prior_term.reshape(base_values.shape)
