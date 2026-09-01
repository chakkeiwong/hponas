"""
hponas: HPO with moderate architecture search

R1 Executable Architecture Spike — minimal stack to prove the corrected interfaces.
Tier 0: Production searchers (GP+qLogEI, TPE, Random), schedulers, executors.
Survey chapters 9, 14, 15 define the scope and contracts.
"""

__version__ = "0.1.0"

# Core interfaces
from .space import SearchSpace
from .searchers import Searcher, SobolSearcher, RandomSearcher
from .schedulers import ASHAScheduler
from .executors import Executor, LocalExecutor
from .store import Store

# Tier 0 searchers (optional dependencies)
try:
    from .searchers_tpe import TPESearcher
except ImportError:
    TPESearcher = None

try:
    from .searchers_gp import GPqLogEISearcher
except ImportError:
    GPqLogEISearcher = None

__all__ = [
    "SearchSpace",
    "Searcher",
    "SobolSearcher",
    "RandomSearcher",
    "TPESearcher",
    "GPqLogEISearcher",
    "ASHAScheduler",
    "Executor",
    "LocalExecutor",
    "Store",
]
