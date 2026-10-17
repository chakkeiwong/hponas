"""GP+qLogEI Bayesian Optimization Searcher.

Reference implementation matching LaTeX Section 3.1 "Baseline Methods".
"""

from typing import Optional, Dict, Any
from copy import deepcopy
from itertools import combinations
import math
import threading
import numpy as np
import torch
from botorch.models import SingleTaskGP
from botorch.models.utils.gpytorch_modules import get_covar_module_with_dim_scaled_prior
from botorch.fit import fit_gpytorch_mll
from botorch.acquisition import qLogExpectedImprovement
from botorch.optim import optimize_acqf, optimize_acqf_discrete
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.kernels import ScaleKernel
from hponas.encoding import SpaceEncoder, as_knob_space

from hponas.searchers.base import BaseSearcher
from hponas.searchers.base import PendingSuggestionError
from hponas.capabilities import SearcherCapabilities, MIXED
from hponas.types import Config, SearchSpace, Result


# Preregistered defaults (BUILD_PROGRAM_v3.md)
GP_DEFAULT_KERNEL = "matern52"
GP_DEFAULT_INITIAL_RANDOM = 5
GP_DEFAULT_ACQUISITION_OPTIMIZER = "lbfgs"
GP_DEFAULT_NUM_RESTARTS = 10
# Bound enumeration independently of the objective or observed performance.
GP_MAX_DISCRETE_CHOICES = 4096
GP_MAX_JOINT_COMBINATIONS = 4096
GP_MAX_BATCH = 8
_GP_RUNTIME_LOCK = threading.RLock()


class GPSearcher(BaseSearcher):
    """Gaussian Process with q-Log Expected Improvement.

    Algorithm:
    1. Initial phase: Random sampling (n=5 default)
    2. Fit GP with Matérn 5/2 kernel and dimension-scaled lengthscale prior
    3. Optimize qLogEI acquisition function
    4. Return next config

    Supports continuous, discrete, categorical parameters.
    """

    support = SearcherCapabilities(MIXED, conditionals=True, joint_batch=True)
    max_batch_size = GP_MAX_BATCH

    def __init__(
        self,
        search_space: SearchSpace,
        seed: Optional[int] = None,
        initial_random_samples: int = GP_DEFAULT_INITIAL_RANDOM,
        num_restarts: int = GP_DEFAULT_NUM_RESTARTS,
        kernel: str = GP_DEFAULT_KERNEL,
        maximize: bool = True,
    ):
        """Initialize GP+qLogEI searcher.

        Args:
            search_space: Search space definition
            seed: Random seed for reproducibility
            initial_random_samples: Number of initial random samples
            num_restarts: Number of acquisition optimization restarts
            kernel: GP kernel type (only "matern52" supported)
        """
        # Input validation BEFORE calling parent or external libraries
        if seed is not None:
            if not isinstance(seed, int):
                raise TypeError(f"seed must be int or None, got {type(seed).__name__}")
            if seed < 0:
                raise ValueError(f"seed must be non-negative, got {seed}")

        if not isinstance(initial_random_samples, int) or initial_random_samples < 1:
            raise ValueError(
                f"initial_random_samples must be positive int, got {initial_random_samples}"
            )

        if not isinstance(num_restarts, int) or num_restarts < 1:
            raise ValueError(f"num_restarts must be positive int, got {num_restarts}")

        if kernel != "matern52":
            raise ValueError(f"Only matern52 kernel supported, got {kernel}")
        if not SpaceEncoder(search_space).space.knobs:
            raise ValueError("GP requires a nonempty search space")

        super().__init__(search_space, seed)
        self.seed = seed  # Store seed for torch RNG control
        self.initial_random_samples = initial_random_samples
        self.num_restarts = num_restarts
        self.kernel = kernel
        self.maximize = maximize
        self.n_suggestions = 0
        self.rng = np.random.RandomState(seed)
        self.proposal_batches = []

    def suggest(self) -> Config:
        """Suggest next configuration using GP+qLogEI.

        Returns:
            Next configuration to evaluate
        """
        # Parallel reduction order can change fitted GP parameters and later
        # suggestions, even at the same seed. Fix this numerical execution
        # setting for replay, and restore both caller RNG and thread settings.
        # The lock protects these process-wide torch settings between GP calls.
        with _GP_RUNTIME_LOCK:
            previous_threads = torch.get_num_threads()
            before = deepcopy(self.rng.get_state()), self.n_suggestions, deepcopy(self.proposal_batches)
            try:
                torch.set_num_threads(1)
                with torch.random.fork_rng(devices=[]):
                    return self._suggest_impl()
            except BaseException:
                self.rng.set_state(before[0])
                self.n_suggestions, self.proposal_batches = before[1:]
                raise
            finally:
                torch.set_num_threads(previous_threads)

    def _suggest_impl(self):
        return self._suggest_joint_impl(1)[0]

    def pending_locations(self):
        observed = {r.trial_id for r in self.history}
        return [(tid, config) for tid, config in self.trials.items() if tid not in observed]

    def validate_study_controls(self, max_concurrent, scheduler):
        if max_concurrent > 1:
            self._validate_joint_domain(min(max_concurrent, GP_MAX_BATCH))

    def _validate_joint_domain(self, count):
        if count == 1:
            return
        finite = self._finite_configs()
        if finite is None:
            if any(k.kind != 'continuous' or k.condition is not None for k in as_knob_space(self.search_space).knobs):
                raise ValueError('Joint mixed GP batches require a bounded finite domain')
        elif math.comb(len(finite), min(count, len(finite)//2)) > GP_MAX_JOINT_COMBINATIONS:
            raise ValueError('Joint finite GP enumeration exceeds 4096 candidate sets')

    def suggest_batch(self, count):
        """Joint acquisition for up to count locations; register before asking again.

        Finite exact enumeration is bounded; continuous optimization is numerical.
        Pending locations enter the same posterior sample, not repeated q=1 calls.
        """
        if type(count) is not int or not 1 <= count <= GP_MAX_BATCH:
            raise ValueError('GP batch size must be an integer from 1 to 8')
        if not self.support.joint_batch:
            raise ValueError('This GP variant does not implement joint batch proposals')
        self._validate_joint_domain(count)
        with _GP_RUNTIME_LOCK:
            previous_threads = torch.get_num_threads()
            before = deepcopy(self.rng.get_state()), self.n_suggestions, deepcopy(self.proposal_batches)
            try:
                torch.set_num_threads(1)
                with torch.random.fork_rng(devices=[]):
                    return self._suggest_joint_impl(count)
            except BaseException:
                self.rng.set_state(before[0])
                self.n_suggestions, self.proposal_batches = before[1:]
                raise
            finally:
                torch.set_num_threads(previous_threads)

    def _suggest_joint_impl(self, count):
        # Set torch seed for deterministic BoTorch operations
        # Seed varies with history length to ensure different suggestions
        if self.seed is not None:
            # Defensive check: validate seed state before arithmetic
            if not isinstance(self.seed, int) or self.seed < 0:
                raise RuntimeError(f"Invalid seed state: {self.seed}")
            torch.manual_seed(self.seed + self.n_suggestions)

        self.n_suggestions += 1
        pending = self.pending_locations()
        valid_results = [r for r in self.history if r.is_valid()]
        if len(valid_results) < self.initial_random_samples:
            configs = []
            for _ in range(1024):
                config = self._sample_random()
                if not any(config.values == other.values for other in configs + [c for _, c in pending]):
                    configs.append(config)
                if len(configs) == count:
                    break
            if not configs:
                raise PendingSuggestionError('No distinct GP location available within the sampling bound')
            self.proposal_batches.append({'mode':'initial_random','configs':[c.to_dict() for c in configs],
                'requested':count,'pending_trial_ids':[tid for tid,_ in pending], 'log_acquisition':None})
            return configs

        # Convert to tensors
        X_train, Y_train = self._prepare_training_data(valid_results)

        # Fit GP
        if not self.maximize:
            Y_train = -Y_train
        gp = SingleTaskGP(
            X_train,
            Y_train,
            covar_module=ScaleKernel(
                get_covar_module_with_dim_scaled_prior(
                    ard_num_dims=X_train.shape[-1], use_rbf_kernel=False
                )
            ),
        )
        mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
        fit_gpytorch_mll(mll)

        # Optimize qLogEI acquisition
        best_f = Y_train.max().item()
        pending_x = torch.stack([self._config_to_tensor(c) for _, c in pending]) if pending else None
        qLogEI = qLogExpectedImprovement(gp, best_f=best_f, X_pending=pending_x)

        finite = self._finite_configs()
        if finite is not None:
            # Rounding a continuous acquisition optimum need not maximize the
            # acquisition on the legal domain. Explore untried finite choices
            # before replicating; submitted/pending configurations also count.
            available = [config for config in finite if not any(config.values == c.values for _, c in pending)]
            unseen = [config for config in available if not any(
                config.values == previous.values for previous in self.trials.values()
            )]
            pool = unseen or available
            if not pool:
                raise PendingSuggestionError('All finite GP locations are pending')
            q = min(count, len(pool))
            choices = torch.stack([self._config_to_tensor(config)
                                   for config in pool])
            if q == 1:
                candidate, acq_value = optimize_acqf_discrete(qLogEI, q=1, choices=choices)
            else:
                candidate, acq_value = self._joint_finite(qLogEI, choices, q)
        else:
            # A relaxed optimum rounded into mixed coordinates is not a joint
            # optimum on the legal domain. Retain only the qualified q=1 path.
            if count > 1 and any(k.kind != 'continuous' or k.condition is not None for k in as_knob_space(self.search_space).knobs):
                raise ValueError('Joint mixed GP batches require a bounded finite domain')
            candidate, acq_value = optimize_acqf(
                qLogEI,
                bounds=self._get_bounds(),
                q=count,
                num_restarts=self.num_restarts,
                raw_samples=512,
            )

        if acq_value.numel() != 1 or not torch.isfinite(acq_value).all():
            raise ValueError('Nonfinite or nonscalar GP acquisition value')
        # Convert back to config
        configs = [self._tensor_to_config(row) for row in candidate]
        if any(c.values == other.values for i,c in enumerate(configs) for other in configs[:i] + [v for _,v in pending]):
            raise ValueError('GP acquisition returned duplicate or pending coordinates')
        self.proposal_batches.append({'mode':'joint_qlogei','configs':[c.to_dict() for c in configs],
            'requested':count,'pending_trial_ids':[tid for tid,_ in pending],
            'log_acquisition':float(acq_value.reshape(-1)[0])})
        return configs

    @staticmethod
    def _joint_finite(acquisition, choices, q):
        """Maximize the actual q-point function over every bounded legal set."""
        if math.comb(len(choices), q) > GP_MAX_JOINT_COMBINATIONS:
            raise ValueError('Joint finite GP enumeration exceeds 4096 candidate sets')
        indices = list(combinations(range(len(choices)), q))
        scores = []
        with torch.no_grad():
            for start in range(0, len(indices), 64):
                batch = torch.stack([choices[list(index)] for index in indices[start:start+64]])
                scores.append(acquisition(batch).reshape(-1))
        scores = torch.cat(scores)
        if not torch.isfinite(scores).all():
            raise ValueError('Nonfinite joint GP acquisition values')
        best = int(scores.argmax())
        return choices[list(indices[best])], scores[best]

    def _finite_configs(self):
        """Enumerate a small wholly discrete domain in stable schema order.

        Larger or continuous domains keep the existing continuous relaxation.
        Conditional children appear only in their active branch. No objective
        values or benchmark-specific information enter domain construction.
        """
        knobs = as_knob_space(self.search_space).knobs
        if any(knob.kind == "continuous" for knob in knobs):
            return None
        configurations = [{}]
        for knob in knobs:
            values = (knob.bounds if knob.kind == "categorical"
                      else range(knob.bounds[0], knob.bounds[1] + 1))
            count = (len(knob.bounds) if knob.kind == "categorical"
                     else knob.bounds[1] - knob.bounds[0] + 1)
            expanded = []
            for config in configurations:
                if knob.condition and config.get(knob.condition[0]) != knob.condition[1]:
                    expanded.append(config)
                else:
                    if len(expanded) + count > GP_MAX_DISCRETE_CHOICES:
                        return None
                    expanded.extend({**config, knob.name: value} for value in values)
            if len(expanded) > GP_MAX_DISCRETE_CHOICES:
                return None
            configurations = expanded
        return [Config(values=config) for config in configurations]

    def _sample_random(self) -> Config:
        """Sample random configuration, supporting both SearchSpace APIs.

        Returns:
            Random configuration from search space
        """
        # Support both hponas.types.SearchSpace and hponas.space.SearchSpace
        if hasattr(self.search_space, "sample_random"):
            # Old API: hponas.types.SearchSpace
            return self.search_space.sample_random(seed=self.rng.randint(0, 2**31))
        elif hasattr(self.search_space, "sample_config"):
            # New API: hponas.space.SearchSpace
            config_dict = self.search_space.sample_config(rng=self.rng)
            return Config(values=config_dict)
        else:
            raise TypeError(
                f"SearchSpace must have either sample_random() or sample_config() method"
            )

    def _prepare_training_data(self, results: list) -> tuple:
        """Convert results to training tensors.

        Args:
            results: List of valid results

        Returns:
            (X_train, Y_train) tensors
        """
        # Input validation
        if not results:
            raise ValueError("Cannot prepare training data from empty results list")
        if not all(r.is_valid() for r in results):
            raise ValueError("All results must be valid for GP training")

        X_list = []
        Y_list = []

        for result in results:
            # Retrieve config from stored mapping
            if result.trial_id not in self.trials:
                continue  # Skip if mapping not found

            config = self.trials[result.trial_id]

            # Convert to tensors
            x = self._config_to_tensor(config)
            y = torch.tensor([result.objective_value], dtype=torch.float64)
            X_list.append(x)
            Y_list.append(y)

        if len(X_list) == 0:
            raise ValueError("No valid training data found")

        X_train = torch.stack(X_list)
        Y_train = torch.stack(Y_list)  # Shape: (n, 1) - no extra unsqueeze needed
        return X_train, Y_train

    def _config_to_tensor(self, config: Config) -> torch.Tensor:
        """Convert config to tensor representation.

        Args:
            config: Configuration

        Returns:
            Tensor of shape (d,)
        """
        return torch.tensor(
            SpaceEncoder(self.search_space).encode(config), dtype=torch.float64
        )

    def _tensor_to_config(self, tensor: torch.Tensor) -> Config:
        """Convert tensor back to config.

        Args:
            tensor: Tensor of shape (d,)

        Returns:
            Configuration
        """
        return Config(
            values=SpaceEncoder(self.search_space).decode(tensor.detach().cpu().numpy())
        )

    def _get_bounds(self) -> torch.Tensor:
        """Get optimization bounds (all in [0, 1] after normalization).

        Returns:
            Bounds tensor of shape (2, d)
        """
        # Support both APIs
        if hasattr(self.search_space, "dim"):
            # Check if dim is a property or method
            dim_attr = getattr(self.search_space, "dim")
            if callable(dim_attr):
                d = dim_attr()  # Old API: method
            else:
                d = dim_attr  # New API: property
        else:
            # Fallback: use knobs list directly
            d = len(self.search_space.knobs)

        return torch.tensor([[0.0] * d, [1.0] * d], dtype=torch.float64)

    def get_state(self) -> Dict[str, Any]:
        """Get searcher state for serialization."""
        state = super().get_state()

        # Convert rng_state to JSON-serializable format
        rng_state = self.rng.get_state()
        rng_state_serializable = (
            rng_state[0],  # String
            rng_state[1].tolist(),  # Convert ndarray to list
            rng_state[2],  # Int
            rng_state[3],  # Int
            rng_state[4],  # Float
        )

        state.update(
            {
                "initial_random_samples": self.initial_random_samples,
                "num_restarts": self.num_restarts,
                "kernel": self.kernel,
                "maximize": self.maximize,
                "n_suggestions": self.n_suggestions,
                "rng_state": rng_state_serializable,
                'pending_trial_ids': [tid for tid,_ in self.pending_locations()],
                'proposal_batches': deepcopy(self.proposal_batches),
            }
        )
        return state

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore searcher state from serialization."""
        observed = {r['trial_id'] for r in state['history']}
        pending = [tid for tid in state.get('trials', {}) if tid not in observed]
        if state.get('pending_trial_ids', pending) != pending:
            raise ValueError('GP pending locations differ from trial/observation ledgers')
        batches = state.get('proposal_batches', [])
        if not isinstance(batches, list):
            raise ValueError('GP batch proposal ledger must be a list')
        for batch in batches:
            if (not isinstance(batch, dict) or set(batch) != {'mode','configs','requested','pending_trial_ids','log_acquisition'}
                    or batch['mode'] not in {'initial_random','joint_qlogei'}
                    or type(batch['requested']) is not int or not 1 <= batch['requested'] <= GP_MAX_BATCH
                    or not isinstance(batch['configs'], list) or not 1 <= len(batch['configs']) <= batch['requested']
                    or not isinstance(batch['pending_trial_ids'], list)
                    or any(not isinstance(t, str) for t in batch['pending_trial_ids'])
                    or len(set(batch['pending_trial_ids'])) != len(batch['pending_trial_ids'])):
                raise ValueError('Invalid GP batch proposal record')
            score = batch['log_acquisition']
            if (batch['mode'] == 'initial_random' and score is not None or
                    batch['mode'] != 'initial_random' and (type(score) not in (int,float) or not math.isfinite(score))):
                raise ValueError('Invalid GP acquisition score')
            for row in batch['configs']:
                as_knob_space(self.search_space).validate_config(Config(**row).values)
        super().set_state(state)
        self.initial_random_samples = state["initial_random_samples"]
        self.num_restarts = state["num_restarts"]
        self.kernel = state["kernel"]
        self.maximize = state.get("maximize", True)
        self.n_suggestions = state.get("n_suggestions", len(self.history))

        # Convert rng_state from serializable format back to numpy format
        rng_state_serializable = state["rng_state"]
        rng_state = (
            rng_state_serializable[0],  # String
            np.array(rng_state_serializable[1]),  # Convert list back to ndarray
            rng_state_serializable[2],  # Int
            rng_state_serializable[3],  # Int
            rng_state_serializable[4],  # Float
        )
        self.rng.set_state(rng_state)
        self.proposal_batches = deepcopy(state.get('proposal_batches', []))
