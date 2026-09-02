"""
Multi-objective searchers: qLogNEHVI, Chebyshev scalarization, NSGA-II.

Survey reference: Ch 7 (multi-objective methods), Ch 4 (Bayesian MO).
BUILD_PROGRAM_v2.md lines 147: MO stack (16 engineer-days).

Tier 1 MO stack:
- qLogNEHVI: GP with log expected hypervolume improvement
- Chebyshev: scalarization fallback
- NSGA-II: evolutionary multi-objective optimizer

Validation: V09 (hypervolume over budget), V11a (MO veto logic).
"""

from __future__ import annotations

import numpy as np
from typing import Any, Optional

from .space import SearchSpace
from .searchers import Searcher

try:
    from botorch.models import SingleTaskGP
    from botorch.acquisition.multi_objective import (
        qLogNoisyExpectedHypervolumeImprovement,
    )
    from botorch.optim import optimize_acqf
    from botorch.utils.transforms import normalize, unnormalize
    from botorch.utils.multi_objective import Hypervolume
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from botorch.fit import fit_gpytorch_mll
    import torch
    BOTORCH_AVAILABLE = True
    BOTORCH_IMPORT_ERROR: str | None = None
except ImportError as _e:  # record why, so a silent False is never mistaken for "not installed"
    BOTORCH_AVAILABLE = False
    BOTORCH_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"


class qLogNEHVISearcher(Searcher):
    """
    Multi-objective Bayesian optimization with log expected hypervolume improvement.

    Survey: Ch 7 multi-objective methods, qLogNEHVI from BoTorch.

    Features:
    - Gaussian process modeling of Pareto front
    - Log expected hypervolume improvement acquisition
    - Reference point adaptation
    - Continuous + ordinal knobs (via one-hot encoding)

    Limitations (Tier 1):
    - Continuous/ordinal only (categorical support deferred to Tier 2)
    - 2-3 objectives (high-dimensional MO deferred)
    """

    def __init__(
        self,
        space: SearchSpace,
        objectives: list[str],
        reference_point: Optional[np.ndarray] = None,
        seed: int = 0
    ):
        """
        Initialize qLogNEHVI searcher.

        Args:
            space: Search space
            objectives: List of objective names (minimize all by default)
            reference_point: Reference point for hypervolume (anti-ideal point)
            seed: Random seed
        """
        if not BOTORCH_AVAILABLE:
            raise ImportError(
                "qLogNEHVISearcher requires botorch. Underlying import error: "
                f"{BOTORCH_IMPORT_ERROR}"
            )

        self.space = space
        self.objectives = objectives
        self.n_objectives = len(objectives)
        self.seed = seed

        # Validate objectives
        if self.n_objectives < 2:
            raise ValueError("qLogNEHVI requires at least 2 objectives")
        if self.n_objectives > 3:
            raise ValueError("Tier 1: qLogNEHVI supports 2-3 objectives only")

        # Reference point (anti-ideal, for hypervolume computation)
        if reference_point is None:
            # Default: slightly worse than origin
            self.reference_point = np.ones(self.n_objectives) * 1.1
        else:
            self.reference_point = np.array(reference_point)

        # Storage
        self._X: list[np.ndarray] = []  # Configurations (normalized)
        self._Y: list[np.ndarray] = []  # Objectives (raw)

        # Random state
        self.rng = np.random.RandomState(seed)
        torch.manual_seed(seed)

        # Check knob support
        for knob in space.knobs:
            if knob.kind == "categorical":
                raise ValueError(f"Tier 1: qLogNEHVI doesn't support categorical knobs yet")

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare what this searcher supports (Ch 15 contract)."""
        return {
            "knob_kinds": ["continuous", "ordinal"],
            "conditionals": False,
            "multi_objective": True,
            "prior": False,
            "max_dim": 20,
        }

    def propose(self, n: int = 1) -> list[dict[str, Any]]:
        """
        Propose n configurations.

        Returns:
            List of configurations (dicts)
        """
        if len(self._X) < 2 * len(self.space.knobs):
            # Initial random sampling (Sobol-like)
            return self._propose_random(n)

        # BO acquisition
        return self._propose_bo(n)

    def _denormalize_knob(self, u: float, knob) -> Any:
        """Map u in [0, 1] to a knob value, honouring the declared transform."""
        low, high = knob.bounds
        if knob.transform == "log":
            val = float(np.exp(np.log(low) + u * (np.log(high) - np.log(low))))
        else:
            val = float(low + u * (high - low))
        if knob.kind == "ordinal":
            return int(np.clip(round(val), low, high))
        return val

    def _propose_random(self, n: int) -> list[dict[str, Any]]:
        """Random sampling for initialization."""
        configs = []
        for _ in range(n):
            config = {}
            for knob in self.space.knobs:
                u = self.rng.uniform(0, 1)
                config[knob.name] = self._denormalize_knob(u, knob)
            configs.append(config)
        return configs

    def _propose_bo(self, n: int) -> list[dict[str, Any]]:
        """Bayesian optimization via qLogNEHVI."""
        # Convert data to tensors
        X_train = torch.tensor(np.array(self._X), dtype=torch.float64)
        Y_train = torch.tensor(np.array(self._Y), dtype=torch.float64)

        # Fit GP model for each objective
        models = []
        for obj_idx in range(self.n_objectives):
            y_obj = Y_train[:, obj_idx].unsqueeze(-1)

            model = SingleTaskGP(X_train, y_obj)
            mll = ExactMarginalLogLikelihood(model.likelihood, model)
            fit_gpytorch_mll(mll)

            models.append(model)

        # Compute current Pareto front for reference
        pareto_mask = self._compute_pareto_mask(Y_train.numpy())
        pareto_Y = Y_train[pareto_mask]

        # qLogNEHVI acquisition function
        ref_point_tensor = torch.tensor(self.reference_point, dtype=torch.float64)

        acq = qLogNoisyExpectedHypervolumeImprovement(
            model=models[0],  # Single model for now (Tier 1 simplification)
            ref_point=ref_point_tensor,
            X_baseline=X_train,
            prune_baseline=True,
        )

        # Optimize acquisition
        bounds = torch.tensor([[0.0] * len(self.space.knobs), [1.0] * len(self.space.knobs)], dtype=torch.float64)

        candidates, _ = optimize_acqf(
            acq_function=acq,
            bounds=bounds,
            q=n,
            num_restarts=10,
            raw_samples=512,
        )

        # Convert back to configs
        configs = []
        for candidate in candidates:
            config = self._tensor_to_config(candidate.numpy())
            configs.append(config)

        return configs

    def _tensor_to_config(self, x: np.ndarray) -> dict[str, Any]:
        """Convert normalized tensor to config dict."""
        config = {}
        for i, knob in enumerate(self.space.knobs):
            config[knob.name] = self._denormalize_knob(float(x[i]), knob)
        return config

    def _compute_pareto_mask(self, Y: np.ndarray) -> np.ndarray:
        """
        Compute Pareto front mask (non-dominated points).

        Args:
            Y: Objectives (n_points, n_objectives)

        Returns:
            Boolean mask of Pareto-optimal points
        """
        n = Y.shape[0]
        pareto_mask = np.ones(n, dtype=bool)

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue

                # Check if j dominates i (all objectives better or equal, at least one strictly better)
                dominates = np.all(Y[j] <= Y[i]) and np.any(Y[j] < Y[i])

                if dominates:
                    pareto_mask[i] = False
                    break

        return pareto_mask

    def observe(self, result: dict[str, Any]) -> None:
        """
        Observe trial result.

        Args:
            result: dict with keys: config, objectives (dict), fidelity, cost
        """
        config = result["config"]
        objectives = result["objectives"]  # dict mapping objective name -> value

        # Normalize config
        x = np.array([self._normalize_knob(config[knob.name], knob) for knob in self.space.knobs])

        # Extract objective values
        y = np.array([objectives[obj_name] for obj_name in self.objectives])

        self._X.append(x)
        self._Y.append(y)

    def _normalize_knob(self, val: Any, knob) -> float:
        """Normalize a knob value to [0, 1], inverting the declared transform."""
        low, high = knob.bounds
        if knob.transform == "log":
            return float(
                (np.log(val) - np.log(low)) / (np.log(high) - np.log(low))
            )
        return float((val - low) / (high - low))

    def state_dict(self) -> dict[str, Any]:
        """Serialize state."""
        return {
            "kind": "qLogNEHVI",
            "seed": self.seed,
            "objectives": self.objectives,
            "reference_point": self.reference_point.tolist(),
            "X": [x.tolist() for x in self._X],
            "Y": [y.tolist() for y in self._Y],
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore state."""
        self.seed = state["seed"]
        self.objectives = state["objectives"]
        self.reference_point = np.array(state["reference_point"])
        self._X = [np.array(x) for x in state["X"]]
        self._Y = [np.array(y) for y in state["Y"]]
        self.rng = np.random.RandomState(self.seed)
        torch.manual_seed(self.seed)


class ChebyshevSearcher(Searcher):
    """
    Multi-objective optimization via Chebyshev scalarization.

    Survey: Ch 7 multi-objective methods, Chebyshev scalarization as fallback.

    Features:
    - Converts multi-objective to single-objective via weighted Chebyshev
    - Works with any single-objective searcher (GP, TPE, Random)
    - No BoTorch dependency (pure numpy)
    - Reference point adaptation from observed data

    Method:
        Chebyshev scalarization: max_i w_i * |y_i - r_i|
        where w_i are weights, y_i objectives, r_i reference point

    This is a fallback when qLogNEHVI fails or BoTorch unavailable.
    """

    def __init__(
        self,
        space: SearchSpace,
        objectives: list[str],
        weights: Optional[np.ndarray] = None,
        reference_point: Optional[np.ndarray] = None,
        base_searcher: str = "random",
        seed: int = 0
    ):
        """
        Initialize Chebyshev searcher.

        Args:
            space: Search space
            objectives: List of objective names (minimize all)
            weights: Weights for Chebyshev (default: uniform)
            reference_point: Reference point (default: anti-ideal from data)
            base_searcher: Base searcher ("random", "gp", "tpe")
            seed: Random seed
        """
        self.space = space
        self.objectives = objectives
        self.n_objectives = len(objectives)
        self.seed = seed
        self.base_searcher_type = base_searcher

        # Weights (default: uniform)
        if weights is None:
            self.weights = np.ones(self.n_objectives) / self.n_objectives
        else:
            self.weights = np.array(weights)

        # Reference point (updated from data)
        if reference_point is None:
            self.reference_point = np.ones(self.n_objectives) * 1.1
        else:
            self.reference_point = np.array(reference_point)

        # Storage
        self._configs: list[dict] = []
        self._objectives: list[np.ndarray] = []
        self._scalarized: list[float] = []

        # Base searcher for single-objective optimization
        self._init_base_searcher()

    def _init_base_searcher(self):
        """Initialize base single-objective searcher."""
        if self.base_searcher_type == "random":
            from .searchers import RandomSearcher
            self.base_searcher = RandomSearcher(self.space, seed=self.seed)
        elif self.base_searcher_type == "gp":
            from .searchers_gp import GPqLogEISearcher
            self.base_searcher = GPqLogEISearcher(self.space, seed=self.seed)
        elif self.base_searcher_type == "tpe":
            from .searchers_tpe import TPESearcher
            self.base_searcher = TPESearcher(self.space, seed=self.seed)
        else:
            raise ValueError(f"Unknown base searcher: {self.base_searcher_type}")

    def _scalarize(self, objectives: np.ndarray) -> float:
        """
        Chebyshev scalarization.

        Args:
            objectives: Array of objective values (n_objectives,)

        Returns:
            Scalarized value (minimize)
        """
        # Chebyshev: max_i w_i * |y_i - r_i|
        deviations = np.abs(objectives - self.reference_point)
        weighted = self.weights * deviations
        return np.max(weighted)

    def propose(self, n: int = 1) -> list[dict[str, Any]]:
        """
        Propose n configurations.

        Delegates to base searcher (scalarized objective).
        """
        return self.base_searcher.propose(n)

    def observe(self, result: dict[str, Any]) -> None:
        """
        Observe trial result.

        Args:
            result: dict with keys: config, objectives (dict), fidelity, cost
        """
        config = result["config"]
        objectives_dict = result["objectives"]

        # Extract objective values
        objectives = np.array([objectives_dict[obj_name] for obj_name in self.objectives])

        # Scalarize
        scalarized_value = self._scalarize(objectives)

        # Store
        self._configs.append(config)
        self._objectives.append(objectives)
        self._scalarized.append(scalarized_value)

        # Update reference point (anti-ideal: worst on each objective)
        if len(self._objectives) > 0:
            all_objs = np.array(self._objectives)
            self.reference_point = np.max(all_objs, axis=0) * 1.1

        # Observe scalarized value in base searcher
        self.base_searcher.observe({
            "config": config,
            "value": scalarized_value,
            "fidelity": result.get("fidelity", 1.0),
            "cost": result.get("cost", 1.0)
        })

    def state_dict(self) -> dict[str, Any]:
        """Serialize state."""
        return {
            "kind": "Chebyshev",
            "seed": self.seed,
            "objective_names": self.objectives,
            "weights": self.weights.tolist(),
            "reference_point": self.reference_point.tolist(),
            "base_searcher_type": self.base_searcher_type,
            "base_searcher_state": self.base_searcher.state_dict(),
            "configs": self._configs,
            "objective_values": [obj.tolist() for obj in self._objectives],
            "scalarized": self._scalarized,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore state."""
        self.seed = state["seed"]
        self.objectives = state["objective_names"]
        self.weights = np.array(state["weights"])
        self.reference_point = np.array(state["reference_point"])
        self.base_searcher_type = state["base_searcher_type"]

        self._init_base_searcher()
        self.base_searcher.load_state_dict(state["base_searcher_state"])

        self._configs = state["configs"]
        self._objectives = [np.array(obj) for obj in state["objective_values"]]
        self._scalarized = state["scalarized"]


class NSGAIISearcher(Searcher):
    """
    NSGA-II: Non-dominated Sorting Genetic Algorithm II.

    Survey: Ch 7 multi-objective methods, evolutionary algorithms.

    Features:
    - Fast non-dominated sorting
    - Crowding distance for diversity
    - Tournament selection
    - Simulated binary crossover (SBX)
    - Polynomial mutation

    Reference: Deb et al. (2002) "A fast and elitist multiobjective genetic
    algorithm: NSGA-II"
    """

    def __init__(
        self,
        space: SearchSpace,
        objectives: list[str],
        population_size: int = 50,
        crossover_prob: float = 0.9,
        mutation_prob: float = 0.1,
        crossover_eta: float = 15.0,
        mutation_eta: float = 20.0,
        seed: int = 0
    ):
        """
        Initialize NSGA-II searcher.

        Args:
            space: Search space
            objectives: List of objective names (minimize all)
            population_size: Population size (must be even)
            crossover_prob: Crossover probability
            mutation_prob: Mutation probability per knob
            crossover_eta: Distribution index for SBX crossover
            mutation_eta: Distribution index for polynomial mutation
            seed: Random seed
        """
        self.space = space
        self.objectives = objectives
        self.n_objectives = len(objectives)
        self.population_size = population_size if population_size % 2 == 0 else population_size + 1
        self.crossover_prob = crossover_prob
        self.mutation_prob = mutation_prob
        self.crossover_eta = crossover_eta
        self.mutation_eta = mutation_eta
        self.seed = seed

        self.rng = np.random.RandomState(seed)

        # Storage
        self._population: list[dict] = []  # Current population configs
        self._objectives_pop: list[np.ndarray] = []  # Objectives for population
        self._archive: list[tuple[dict, np.ndarray]] = []  # All evaluated (config, objectives)

        # Continuous knobs only for now (categorical deferred to Tier 2)
        self._continuous_knobs = [
            k for k in space.knobs if k.kind in ("continuous", "ordinal")
        ]
        self._n_params = len(self._continuous_knobs)

    def _pareto_dominates(self, obj_a: np.ndarray, obj_b: np.ndarray) -> bool:
        """Check if obj_a dominates obj_b (minimize all objectives)."""
        return np.all(obj_a <= obj_b) and np.any(obj_a < obj_b)

    def _fast_non_dominated_sort(
        self, objectives: list[np.ndarray]
    ) -> list[list[int]]:
        """
        Fast non-dominated sorting.

        Returns:
            List of fronts, each front is a list of indices into objectives.
        """
        n = len(objectives)
        domination_count = np.zeros(n, dtype=int)  # How many dominate this solution
        dominated_solutions = [[] for _ in range(n)]  # Which solutions this dominates

        for i in range(n):
            for j in range(i + 1, n):
                if self._pareto_dominates(objectives[i], objectives[j]):
                    dominated_solutions[i].append(j)
                    domination_count[j] += 1
                elif self._pareto_dominates(objectives[j], objectives[i]):
                    dominated_solutions[j].append(i)
                    domination_count[i] += 1

        fronts = []
        current_front = [i for i in range(n) if domination_count[i] == 0]

        while current_front:
            fronts.append(current_front)
            next_front = []
            for i in current_front:
                for j in dominated_solutions[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        next_front.append(j)
            current_front = next_front

        return fronts

    def _crowding_distance(
        self, front_indices: list[int], objectives: list[np.ndarray]
    ) -> np.ndarray:
        """
        Compute crowding distance for a front.

        Returns:
            Array of crowding distances for each solution in the front.
        """
        n = len(front_indices)
        if n == 0:
            return np.array([])
        if n <= 2:
            return np.full(n, np.inf)

        distances = np.zeros(n)

        for obj_idx in range(self.n_objectives):
            # Sort by this objective
            obj_values = np.array([objectives[i][obj_idx] for i in front_indices])
            sorted_indices = np.argsort(obj_values)

            # Boundary points get infinite distance
            distances[sorted_indices[0]] = np.inf
            distances[sorted_indices[-1]] = np.inf

            # Normalize range
            obj_range = obj_values[sorted_indices[-1]] - obj_values[sorted_indices[0]]
            if obj_range == 0:
                continue

            # Interior points
            for i in range(1, n - 1):
                distances[sorted_indices[i]] += (
                    obj_values[sorted_indices[i + 1]] - obj_values[sorted_indices[i - 1]]
                ) / obj_range

        return distances

    def _tournament_selection(
        self, fronts: list[list[int]], crowding: dict[int, float]
    ) -> int:
        """Tournament selection: pick better of two random solutions."""
        i, j = self.rng.choice(len(self._population), size=2, replace=False)

        # Find fronts
        front_i = next((f for f, front in enumerate(fronts) if i in front), None)
        front_j = next((f for f, front in enumerate(fronts) if j in front), None)

        if front_i < front_j:
            return i
        elif front_j < front_i:
            return j
        else:
            # Same front: use crowding distance
            return i if crowding[i] > crowding[j] else j

    def _sbx_crossover(self, parent1: np.ndarray, parent2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Simulated binary crossover (SBX).

        Args:
            parent1, parent2: Normalized parameter vectors [0, 1]

        Returns:
            Two offspring
        """
        child1 = parent1.copy()
        child2 = parent2.copy()

        for i in range(self._n_params):
            if self.rng.rand() > 0.5:
                continue

            p1, p2 = parent1[i], parent2[i]
            if abs(p1 - p2) < 1e-9:
                continue

            # SBX
            if p1 < p2:
                beta = 1.0 + (2.0 * p1) / (p2 - p1)
            else:
                beta = 1.0 + (2.0 * (1.0 - p1)) / (p1 - p2)

            alpha = 2.0 - beta ** (-(self.crossover_eta + 1.0))

            u = self.rng.rand()
            if u <= 1.0 / alpha:
                beta_q = (u * alpha) ** (1.0 / (self.crossover_eta + 1.0))
            else:
                beta_q = (1.0 / (2.0 - u * alpha)) ** (1.0 / (self.crossover_eta + 1.0))

            child1[i] = 0.5 * ((p1 + p2) - beta_q * abs(p2 - p1))
            child2[i] = 0.5 * ((p1 + p2) + beta_q * abs(p2 - p1))

        # Clip to [0, 1]
        child1 = np.clip(child1, 0.0, 1.0)
        child2 = np.clip(child2, 0.0, 1.0)

        return child1, child2

    def _polynomial_mutation(self, individual: np.ndarray) -> np.ndarray:
        """
        Polynomial mutation.

        Args:
            individual: Normalized parameter vector [0, 1]

        Returns:
            Mutated individual
        """
        mutated = individual.copy()

        for i in range(self._n_params):
            if self.rng.rand() > self.mutation_prob:
                continue

            y = mutated[i]
            delta = min(y, 1.0 - y)

            u = self.rng.rand()
            if u < 0.5:
                delta_q = (2.0 * u) ** (1.0 / (self.mutation_eta + 1.0)) - 1.0
            else:
                delta_q = 1.0 - (2.0 * (1.0 - u)) ** (1.0 / (self.mutation_eta + 1.0))

            mutated[i] = y + delta_q * delta

        # Clip to [0, 1]
        return np.clip(mutated, 0.0, 1.0)

    def _config_to_vector(self, config: dict) -> np.ndarray:
        """Convert config to normalized parameter vector [0, 1]."""
        vector = np.zeros(self._n_params)
        for i, knob in enumerate(self._continuous_knobs):
            value = config[knob.name]
            lower, upper = knob.bounds
            vector[i] = (value - lower) / (upper - lower)
        return vector

    def _vector_to_config(self, vector: np.ndarray) -> dict:
        """Convert normalized parameter vector to config."""
        config = {}
        for i, knob in enumerate(self._continuous_knobs):
            lower, upper = knob.bounds
            value = lower + vector[i] * (upper - lower)
            if knob.kind == "ordinal":
                value = int(round(value))
            config[knob.name] = value
        return config

    def propose(self, n: int = 1) -> list[dict[str, Any]]:
        """
        Propose n configurations.

        First generation: random initialization.
        Later generations: selection, crossover, mutation.
        """
        if len(self._population) < self.population_size:
            # Random initialization
            configs = []
            for _ in range(n):
                config = {}
                for knob in self._continuous_knobs:
                    lower, upper = knob.bounds
                    value = self.rng.uniform(lower, upper)
                    if knob.kind == "ordinal":
                        value = int(round(value))
                    config[knob.name] = value
                configs.append(config)
            return configs

        # Evolutionary generation: need full population evaluated
        if len(self._objectives_pop) < self.population_size:
            return []

        # Non-dominated sorting + crowding distance
        fronts = self._fast_non_dominated_sort(self._objectives_pop)

        # Crowding distance for all individuals
        crowding = {}
        for front in fronts:
            distances = self._crowding_distance(front, self._objectives_pop)
            for i, idx in enumerate(front):
                crowding[idx] = distances[i]

        # Generate offspring via selection, crossover, mutation
        offspring_vectors = []
        while len(offspring_vectors) < n:
            # Tournament selection
            parent1_idx = self._tournament_selection(fronts, crowding)
            parent2_idx = self._tournament_selection(fronts, crowding)

            parent1_vec = self._config_to_vector(self._population[parent1_idx])
            parent2_vec = self._config_to_vector(self._population[parent2_idx])

            # Crossover
            if self.rng.rand() < self.crossover_prob:
                child1_vec, child2_vec = self._sbx_crossover(parent1_vec, parent2_vec)
            else:
                child1_vec, child2_vec = parent1_vec.copy(), parent2_vec.copy()

            # Mutation
            child1_vec = self._polynomial_mutation(child1_vec)
            child2_vec = self._polynomial_mutation(child2_vec)

            offspring_vectors.extend([child1_vec, child2_vec])

        # Convert to configs
        configs = [self._vector_to_config(vec) for vec in offspring_vectors[:n]]
        return configs

    def observe(self, result: dict[str, Any]) -> None:
        """
        Observe trial result.

        Args:
            result: dict with keys: config, objectives (dict), fidelity, cost
        """
        config = result["config"]
        objectives_dict = result["objectives"]

        # Extract objective values
        objectives = np.array([objectives_dict[obj_name] for obj_name in self.objectives])

        # Add to archive
        self._archive.append((config, objectives))

        # Add to population
        self._population.append(config)
        self._objectives_pop.append(objectives)

        # Environmental selection when population exceeds limit
        if len(self._population) > self.population_size:
            fronts = self._fast_non_dominated_sort(self._objectives_pop)

            # Build new population from fronts
            new_pop = []
            new_objs = []
            for front in fronts:
                if len(new_pop) + len(front) <= self.population_size:
                    # Add entire front
                    for idx in front:
                        new_pop.append(self._population[idx])
                        new_objs.append(self._objectives_pop[idx])
                else:
                    # Add part of front based on crowding distance
                    distances = self._crowding_distance(front, self._objectives_pop)
                    sorted_indices = np.argsort(-distances)  # Descending
                    n_needed = self.population_size - len(new_pop)
                    for i in range(n_needed):
                        idx = front[sorted_indices[i]]
                        new_pop.append(self._population[idx])
                        new_objs.append(self._objectives_pop[idx])
                    break

            self._population = new_pop
            self._objectives_pop = new_objs

    def state_dict(self) -> dict[str, Any]:
        """Serialize state."""
        return {
            "kind": "NSGA-II",
            "seed": self.seed,
            "objectives": self.objectives,
            "population_size": self.population_size,
            "crossover_prob": self.crossover_prob,
            "mutation_prob": self.mutation_prob,
            "crossover_eta": self.crossover_eta,
            "mutation_eta": self.mutation_eta,
            "population": self._population,
            "objectives_pop": [obj.tolist() for obj in self._objectives_pop],
            "archive": [(cfg, obj.tolist()) for cfg, obj in self._archive],
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore state."""
        self.seed = state["seed"]
        self.objectives = state["objectives"]
        self.population_size = state["population_size"]
        self.crossover_prob = state["crossover_prob"]
        self.mutation_prob = state["mutation_prob"]
        self.crossover_eta = state["crossover_eta"]
        self.mutation_eta = state["mutation_eta"]

        self.rng = np.random.RandomState(self.seed)

        self._population = state["population"]
        self._objectives_pop = [np.array(obj) for obj in state["objectives_pop"]]
        self._archive = [(cfg, np.array(obj)) for cfg, obj in state["archive"]]
