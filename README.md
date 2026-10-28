# HPO-NAS

Reusable HPO and moderate architecture-coordinate NAS for the model families used by a universal retail bank. The [product contract](docs/program/BANK_HPO_NAS_PRODUCT_CONTRACT.md) covers prediction and forecasting, causal/policy models, financial inference, constrained neural solvers, valuation and allocation. Models, data and frameworks stay caller-owned; sibling repositories are not runtime dependencies. The initial qualified search spaces have roughly 2–10 coordinates. General cell search, supernets and weight sharing remain outside scope.

**Status:** The adopted finite local program and RL-LQR-09 dimensional study are summarized in [results](docs/results/README.md), with numerical limitations retained. The [master](CONSOLIDATED_MASTER_AUTHORITY.md) and [product contract](docs/program/BANK_HPO_NAS_PRODUCT_CONTRACT.md) define scope. Raw qualification evidence and original history are preserved locally, outside Git. This summary-only checkout does not itself requalify historical results. Buildable manual sources are in [hpo-survey/published](hpo-survey/published/README.md).

## Install

Ordinary clones contain source, tests, documentation and concise summaries. Git LFS and raw evidence downloads are not required. See the [artifact storage policy](docs/ARTIFACT_STORAGE.md) for the local archive and historical reconstruction.

Python 3.12+ is required. Clean CPU installations are checked on Python 3.12 and 3.13; other versions and platforms are not verified. Keep the environment separate from other projects.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
# Optional components:
python -m pip install -e '.[ray,tpe,cmaes,rl,validation,test]'
```

The RL extra pins Brax to the tested Git revision because its PyPI 0.14.2 release is incompatible with the supported JAX 0.11 line. Campaign metadata records installed versions and dependency source URLs. GPU JAX installation is hardware-specific; CPU runs work with the declared extra.

## Quick start

The wheel ships two plain caller-owned fitted models. Each uses the public
Study/Store APIs, a persisted declaration, disjoint tuning/final rows and seeds,
work reservations, model artifacts and an explicit recovery path. Run from any
directory with the installed package:

```bash
python -m hponas.quickstart --model hinge --output /tmp/hinge-study
python -m hponas.quickstart --model allocation --output /tmp/allocation-study
python -m hponas.quickstart --model hinge --output /tmp/hinge-study --resume
```

Use a new empty output directory for a new run. The hinge model fits a ReLU
readout while searching hidden width and ridge strength; the allocation model
tunes a projected-gradient solver for an exact two-asset problem. Four
proposals cover each small domain. The command reports actual regret against exact
finite references, with no stochastic precision or real-bank performance claim.
See [caller model examples](docs/CALLER_MODELS.md) for the mathematics, artifacts
and code to adapt. No sibling project or fixture inheritance is required.

The following arithmetic tutorial illustrates the explicit legacy compatibility
path. Ordinary model studies require a declaration:

```python
from hponas import GPSearcher, Knob, LocalExecutor, SearchSpace, Study

space = SearchSpace([
    Knob('x', 'continuous', (0.0, 1.0)),
    Knob('width', 'ordinal', (8, 32)),
])

def objective(config):
    return (config['x'] - 0.3)**2 + ((config['width'] - 16) / 32)**2

study = Study(
    GPSearcher(space, seed=42), LocalExecutor(), objective,
    budget=10, maximize=False, study_name='example', checkpoint_dir='checkpoints',
    legacy_reason='Exposed arithmetic tutorial; no protected performance claim',
)
result = study.run()
print(result.best_config.values, result.best_value)
```

Objectives receive a configuration dictionary. They can also declare `fidelity`, `seed`, and `trial_id` parameters. Return a scalar or a dictionary with `value`, `cost` (seconds), `metadata`, and file-path `artifacts`. A `Study` budget counts new configurations; ASHA promotions add evaluations. `total_cost` includes all completed/failed attempts reported by the executor, not unmeasured work lost when the driver dies.

Resume with a fresh executor and searcher, then load the checkpoint before calling `run()`:

```python
resumed = Study(GPSearcher(space), LocalExecutor(), objective,
                legacy_reason='Exposed arithmetic tutorial; no protected performance claim')
resumed.load_checkpoint('checkpoints/example_checkpoint.json')
result = resumed.run()
```

Committed results are not dispatched again. Pending work can execute again after a crash; use `trial_id` to make external side effects idempotent. Legacy checkpoints use schema 3 and require the same persisted reason. Old snapshots without a reason require explicit migration or their retained source. Declared evaluation uses schema 4, or schema 5 with resource reservations. Batch observations commit in dispatch order. A Store snapshot is authoritative if both SQLite and a JSON projection are configured; load from the Store after an interrupted projection write.

The arithmetic example above reports `legacy_unqualified` evaluation. The shipped model examples use declared evaluation; [the evaluation contract](docs/EVALUATION.md) and [the checkout example](examples/declared_tuning.py) explain how to adapt it. Final measurements stay out of searcher history; failed or incomplete evaluation remains visible.

[StudyBudget](docs/BUDGETS.md) separately declares configuration count, work units, tuning/final reserves, elapsed caps and worker capacity. Method capabilities are checked before dispatch. Recorded work and lost-attempt reservations survive recovery; endpoint time limits report overshoot. Neither resource accounting nor a finite example establishes empirical usefulness.

For public GP studies with several dispatch slots, [joint GP batches](docs/GP_BATCH.md) optimize qLogEI over candidate sets and integrate registered pending locations in the joint posterior. Small finite domains use bounded set enumeration; continuous optimization remains numerical. Proposal sets and observation order survive checkpoints.

[Rung diagnostics](docs/DIAGNOSTICS.md) report paired ranks against full tuning fidelity, with tie handling, counts and missing-data reasons. They describe observed pairs and do not certify safe pruning.

[Complete reports and adapter contracts](docs/REPORTS_AND_ADAPTERS.md) cover Study/Store exports, raw repetitions, curves, constraints, artifacts and recovery. Public Ray execution uses Ray Core; metered studies reserve retries through Study recovery.

ASHA now uses reference quantile promotion with waiting candidates and explicit legacy compatibility. Objectives that declare `reporter` can be paused, pruned, or cancelled while running on Local or Ray executors. Promotions can resume durable checkpoints or explicitly restart and charge repeated work. See [streaming, median pruning, compute limits, and incomplete outcomes](docs/STREAMING_SCHEDULER.md).

The public `SearchSpace` uses `Knob`. `hponas.types.SearchSpace`/`Parameter` remain supported through an adapter. Legacy `propose()` searchers are adapted when passed to Study. Explicitly named legacy modules remain available. Scalar Study does not accept multi-objective searchers.

`CMAESSearcher(space, seed=42)` wraps Optuna/CMA-ES for unconditional continuous spaces, with optional log/logit transforms. Install the `cmaes` extra. Its checkpoints bind the vendor versions and retain pending asks; mixed/conditional spaces are rejected.

`PASHAScheduler(PASHAConfig(...))` in `hponas.schedulers` grows the maximum fidelity only when survivor rankings disagree. Study selects its incumbent at that current fidelity. This may be below the declared full budget; final full-budget evaluation remains a separate workload decision. The older budget-only policy is now named `BudgetedASHAScheduler`/`BudgetedASHAConfig`. Existing budget-only checkpoints must use that policy and cannot be loaded as progressive PASHA. See the [specification repair review](docs/program/SPEC_REPAIR_REVIEW_2026_09_28.md) for the tested envelope.

## Real PPO and validation

The [maintained examples](examples/README.md) run against either checkout or installed library code. They preserve unique run directories and do not certify acceptance. Audited campaigns below require a restored evidence archive and their original source-bound runtime; a summary-only clone is insufficient. Their source fingerprint covers tests, examples, build inputs and protocols omitted from the wheel. A wheel-only invocation is rejected before campaign artifacts are written. Use `python -m tools.check_installed --output receipt.json` from outside the checkout to verify an isolated wheel installation.

```bash
# Real bounded CPU PPO, policy checkpoint, SQLite ledger and separate protected evaluation:
JAX_PLATFORMS=cpu OMP_NUM_THREADS=2 python -m validation.run_validation_with_audit V14
# Independent vendor parity and actual replay/crash/concurrency scenarios:
OMP_NUM_THREADS=2 python -m validation.run_validation_with_audit V01
OMP_NUM_THREADS=2 python -m validation.run_validation_with_audit V02
# Inspect historical mutation cache; this cannot produce a campaign PASS:
python -m validation.run_validation_with_audit V03
# Full mutation run in a new source copy, preserving the existing cache:
python -m validation.run_validation_with_audit V03 --run-mutations
python -m tools.gate_check --phase tier0 --mode dry-run
```

V14 evaluates protected seed 999 only after the search result is committed. `workloads.rl_routine.evaluate_checkpoint` performs this separate evaluation. Passing V14 establishes an executable workflow, not statistical performance.

V04-T0/V05 use self-contained fixed models with independently known tuning answers. Their finite conformance results do not establish general superiority or promote defaults. The previous PPO comparison/pilot/power design is retired under D-SELF-CONTAINED-VALIDATION. See [supported workloads](docs/WORKLOADS.md) and the [historical qualification summary](docs/results/README.md). PRD-01 foundation repairs and BANK-01/GAP-QUALIFICATION completed their historical scope. Current-source qualification and the final independent GAP-01/FINAL-AUDIT have passed.

Every audited run preserves its protocol, raw results, package/source fingerprints, and a V16 receipt under `validation/artifacts/<ID>/<run>/`. Gates reject missing, stale, empty, or inconsistent evidence. See the [current master program](CONSOLIDATED_MASTER_AUTHORITY.md) for execution status.

## Development

Use the [fixed local operations commands](docs/PROGRAM_OPERATIONS.md). The publication roster in docs/lean-checks.json is archive-independent. The full historical test/audit roster additionally requires restored evidence; no archived scientific test is silently treated as passed.

```bash
python -m pip install -e '.[dev,test,ray,tpe,cmaes,validation]'
python -m pytest $(python -c "import json; print(' '.join(json.load(open('docs/lean-checks.json'))['tests']))") -q
python -m ruff check hponas workloads validation tools
python -m compileall -q hponas workloads validation tools examples
```

ASHA, MO-ASHA, multi-objective search, cost-aware search, priors, trust regions, population methods, DEHB and ranked warm starts have retained finite qualification on the accepted source. Optional methods remain opt-in; broader effectiveness is unestablished. ifBO feasibility failed and integration is cancelled.

The supported learned-transport fixture trains an explicit small tanh coupling. The legacy `workloads.sampler_neutra` callable remains ordinary HMC; see [workload identities and limits](docs/WORKLOADS.md). PRD-01 completed the foundation interfaces; GAP-01 restored the omitted vector batching, repeated streaming, TPE scheduling, population, operations, RGPE and installed-caller obligations. Their accepted qualification and final audit remain bound to the historical source. Current-source qualification and the final independent GAP-01/FINAL-AUDIT have passed.

## Optional scientific verification tools

The optional [hponas-scientific-checks package](extensions/scientific-checks/README.md)
provides a public Python API and JSON CLI for finite PI reconstruction, fixed-domain
NAS derivative certificates, exact synthetic references, and deterministic wallet
population enclosures. It is a separate installable distribution, not an added
optimizer or a change to the qualified core wheel. Its [mathematical argument](extensions/scientific-checks/MATHEMATICS.md)
and [SCI-03 plan](docs/program/SCIENTIFIC_DELIVERY_2026_10_25.md) define the supported
scope. Installation and saved-artifact qualification are recorded under
[SCI-03 evidence](docs/program/evidence/2026-10-25/scientific-delivery-03).

The frozen wallet policies have positive synthetic utility bounds versus no action;
selected-versus-likelihood superiority remains unresolved. The six saved ifBO
performance failures and cancelled optimizer integration remain unchanged. These
tools do not establish unseen-model guarantees, unknown-MNAR/causal identification,
general sampler convergence, real-bank effectiveness or production readiness.
