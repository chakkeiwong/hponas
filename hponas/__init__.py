"""HPO-NAS: Hyperparameter and Neural Architecture Search.

A system for moderate architecture-coordinate Neural Architecture Search supporting:
- Bayesian optimization (GP+qLogEI)
- Multi-fidelity optimization (ASHA)
- Multi-objective optimization (qLogNEHVI)
- Random and Sobol baselines
"""

__version__ = "0.1.0"

from hponas.study import Study

__all__ = [
    "Study",
    "__version__",
]
