"""Study: Main API for running optimization."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
import json
import uuid
from pathlib import Path

from hponas.types import Config, Trial, Result, SearchSpace
from hponas.searchers.base import BaseSearcher
from hponas.executors.base import BaseExecutor


@dataclass
class StudyResult:
    """Result of optimization study."""
    best_config: Config
    best_value: float
    history: List[Result]
    n_trials: int
    total_cost: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "best_config": self.best_config.to_dict(),
            "best_value": self.best_value,
            "history": [r.to_dict() for r in self.history],
            "n_trials": self.n_trials,
            "total_cost": self.total_cost,
        }


class Study:
    """Main study class for running HPO/NAS.

    Example:
        >>> from hponas import Study, GPSearcher, LocalExecutor
        >>>
        >>> study = Study(
        ...     searcher=GPSearcher(search_space),
        ...     executor=LocalExecutor(),
        ...     objective_fn=my_objective,
        ...     budget=100,
        ...     maximize=True,
        ... )
        >>> result = study.run()
    """

    def __init__(
        self,
        searcher: BaseSearcher,
        executor: BaseExecutor,
        objective_fn: Callable[[dict], float],
        budget: int = 100,
        maximize: bool = True,
        study_name: Optional[str] = None,
        checkpoint_dir: Optional[Path] = None,
    ):
        """Initialize study.

        Args:
            searcher: Optimization algorithm (GP, Random, etc.)
            executor: Trial execution backend (Local, Ray)
            objective_fn: Function to optimize
            budget: Total number of trials
            maximize: Whether to maximize (True) or minimize (False)
            study_name: Optional study name for tracking
            checkpoint_dir: Directory for checkpoints (None = no checkpointing)
        """
        self.searcher = searcher
        self.executor = executor
        self.objective_fn = objective_fn
        self.budget = budget
        self.maximize = maximize
        self.study_name = study_name or f"study_{uuid.uuid4().hex[:8]}"
        self.checkpoint_dir = checkpoint_dir

        # State
        self.trials: Dict[str, Trial] = {}
        self.results: Dict[str, Result] = {}
        self.n_completed = 0

    def run(self) -> StudyResult:
        """Run optimization study.

        Returns:
            Study result with best config and history
        """
        try:
            for i in range(self.budget):
                # Suggest next config
                config = self.searcher.suggest()

                # Create trial
                trial = Trial(
                    config=config,
                    trial_id=f"{self.study_name}_trial_{i}",
                    fidelity=1.0,
                    status="pending",
                )
                self.trials[trial.trial_id] = trial

                # Register config-trial mapping in searcher for GP training data
                self.searcher.trials[trial.trial_id] = config

                # Execute trial
                result = self.executor.execute(trial, self.objective_fn)
                self.results[trial.trial_id] = result

                # Observe result
                self.searcher.observe(result)
                self.n_completed += 1

                # Checkpoint (if enabled)
                if self.checkpoint_dir is not None and (i + 1) % 10 == 0:
                    self.save_checkpoint()

            # Get best result
            best_result = self.searcher.get_best(maximize=self.maximize)
            if best_result is None:
                raise RuntimeError("No valid results found")

            # Get best config
            best_trial = self.trials[best_result.trial_id]
            best_config = best_trial.config

            # Compute total cost
            total_cost = sum(r.cost for r in self.results.values())

            return StudyResult(
                best_config=best_config,
                best_value=best_result.objective_value,
                history=list(self.results.values()),
                n_trials=self.n_completed,
                total_cost=total_cost,
            )

        finally:
            # Always cleanup
            self.executor.shutdown()

    def save_checkpoint(self) -> None:
        """Save study checkpoint."""
        if self.checkpoint_dir is None:
            return

        checkpoint_dir = Path(self.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            "study_name": self.study_name,
            "budget": self.budget,
            "maximize": self.maximize,
            "n_completed": self.n_completed,
            "trials": {k: v.to_dict() for k, v in self.trials.items()},
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "searcher_state": self.searcher.get_state(),
        }

        checkpoint_path = checkpoint_dir / f"{self.study_name}_checkpoint.json"
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f, indent=2)

    def load_checkpoint(self, checkpoint_path: Path) -> None:
        """Load study checkpoint.

        Args:
            checkpoint_path: Path to checkpoint file
        """
        with open(checkpoint_path, "r") as f:
            checkpoint = json.load(f)

        self.study_name = checkpoint["study_name"]
        self.budget = checkpoint["budget"]
        self.maximize = checkpoint["maximize"]
        self.n_completed = checkpoint["n_completed"]

        # Restore trials
        self.trials = {
            k: Trial(**v) for k, v in checkpoint["trials"].items()
        }

        # Restore results
        self.results = {
            k: Result(**v) for k, v in checkpoint["results"].items()
        }

        # Restore searcher state
        self.searcher.set_state(checkpoint["searcher_state"])

    def get_history(self) -> List[Result]:
        """Get all results so far.

        Returns:
            List of results in order
        """
        return list(self.results.values())

    def get_best_so_far(self) -> Optional[Result]:
        """Get best result seen so far.

        Returns:
            Best result, or None if no valid results
        """
        return self.searcher.get_best(maximize=self.maximize)
