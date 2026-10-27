"""HPO-NAS: Hyperparameter and Neural Architecture Search.

A system for moderate architecture-coordinate Neural Architecture Search supporting:
- Bayesian optimization (GP+qLogEI)
- Multi-fidelity optimization (ASHA)
- Multi-objective optimization (qLogNEHVI)
- Random and Sobol baselines
"""

__version__ = "0.1.0"

from hponas.study import Study, StudyResult, IncompleteStudyError
from hponas.evaluation import StudyDeclaration, EvaluationFold, EvaluationObjective, EvaluationContext
from hponas.population_adapter import AdapterPopulation, PopulationAdapter, PopulationExecutionError
from hponas.adapter_parallel import ParallelAdapterPopulation
from hponas.local_service import ManagedStudyService, DirectoryAlertSink, import_legacy_store, migrate_service, rollback_migration, restore_events
from hponas.backup_security import BackupKeyProvider
from hponas.rgpe import RGPESearcher, prepare_rgpe_history
from hponas.budgets import StudyBudget
from hponas.capabilities import SearcherCapabilities
from hponas.prior_sampling import FiniteGuardedPrior, guarded_probabilities
from hponas.prior_band import PriorBand
from hponas.searchers.prior import FinitePriorSearcher, PriorPendingError
from hponas.searchers.priorband import CategoricalPriorBandSearcher
from hponas.searchers.product_priorband import ProductPriorBandSearcher
from hponas.schedulers_prior import PriorBandScheduler
from hponas.trust_searcher import TrustRegionSearcher
from hponas.cost_searcher import CensoredCostGP, CostAwareProposalSearcher
from hponas.study_mo import MultiObjectiveStudy, MultiObjectiveStudyResult
from hponas.multi_objective import ObjectiveSpec
from hponas.searchers.multi_objective import MultiObjectiveRandomSearcher, MultiObjectiveBayesSearcher, WrappedNSGAIISearcher
from hponas.schedulers_mo import MultiObjectiveScheduler
from hponas.executors.reporting import ProgressReport, ReportDecision
from hponas.space import SearchSpace, Knob
from hponas.types import Config, Trial, Result
from hponas.searchers import CMAESSearcher, GPSearcher, RobustGPSearcher, RandomSearcher, SobolSearcher
from hponas.executors import LocalExecutor, RayExecutor, ResourceExecutor, ResourceSpec, ExecutionContext
from hponas.dehb import DEHBController
from hponas.parallel import run_replicas

__all__ = [
    "Study",
    "StudyDeclaration",
    "StudyBudget",
    "SearcherCapabilities",
    "EvaluationFold",
    "EvaluationObjective",
    "EvaluationContext",
    "AdapterPopulation",
    "ParallelAdapterPopulation",
    "PopulationAdapter",
    "PopulationExecutionError",
    "ManagedStudyService",
    "DirectoryAlertSink",
    "BackupKeyProvider",
    "RGPESearcher",
    "prepare_rgpe_history",
    "import_legacy_store",
    "migrate_service",
    "rollback_migration",
    "restore_events",
    "FiniteGuardedPrior",
    "guarded_probabilities",
    "PriorBand",
    "FinitePriorSearcher",
    "CategoricalPriorBandSearcher",
    "ProductPriorBandSearcher",
    "PriorPendingError",
    "PriorBandScheduler",
    "TrustRegionSearcher",
    "CensoredCostGP",
    "CostAwareProposalSearcher",
    "StudyResult",
    "MultiObjectiveStudy",
    "MultiObjectiveStudyResult",
    "MultiObjectiveRandomSearcher",
    "MultiObjectiveBayesSearcher",
    "WrappedNSGAIISearcher",
    "MultiObjectiveScheduler",
    "ObjectiveSpec",
    "IncompleteStudyError",
    "ProgressReport",
    "ReportDecision",
    "SearchSpace",
    "Knob",
    "Config",
    "Trial",
    "Result",
    "GPSearcher",
    "RobustGPSearcher",
    "CMAESSearcher",
    "RandomSearcher",
    "SobolSearcher",
    "LocalExecutor",
    "RayExecutor",
    "ResourceExecutor",
    "ResourceSpec",
    "ExecutionContext",
    "DEHBController",
    "run_replicas",
    "__version__",
]
