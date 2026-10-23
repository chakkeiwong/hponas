# Ranked warm starts and RGPE

Warm starts remain opt-in. The implementation transfers candidate configurations,
then evaluates them on the new task. It never imports old objective values as
new observations. The ranked wrapper is separate from the opt-in RGPE searcher
described below. Neither establishes an empirical V12 speedup.

After a stored study finishes, retain its history with explicit model, task and
objective identities:

```python
store.freeze_warm_history(
    "completed-study", task_id="training-task-1", model_family="ridge",
    task_domain="linear-risk", objective_key="coefficient-risk-v1",
    endpoint_fidelity=1.0,
)
```

This captures the completed study and trials in one SQLite transaction. The
snapshot records the current time and cannot be backdated. Later edits to live
study rows do not change the retained history. Repeating the same declaration
returns the original snapshot; changing its identity is refused.

Declare the new target and history cutoff before querying:

```python
import time
from hponas import Study, RandomSearcher, LocalExecutor
from hponas.warm_history import target_context
from hponas.warm_start import RankedWarmStartSearcher

context = target_context(
    space, study_id="new-study", task_id="held-out-task",
    model_family="ridge", task_domain="linear-risk",
    objective_key="coefficient-risk-v1", direction="minimize",
    history_cutoff=time.time(), endpoint_fidelity=1.0,
)
searcher = RankedWarmStartSearcher.from_store(
    RandomSearcher(space, seed=7), store, context=context, n=8,
)
study = Study(searcher, LocalExecutor(), objective, budget=32,
              study_name="new-study", maximize=False, store=store,
              declaration=declaration)  # Declare target tuning and final roles first.
```

Selection requires matching objective direction and meaning, model family, task
domain, endpoint fidelity and complete search-space coordinates, including
transforms and conditions. The target study and held-out tasks are excluded.
Each eligible study supplies empirical mid-ranks; raw values from different
studies are never compared. Ties use study/trial identity, and repeated physical
configurations are removed. With no eligible history, the base sequence runs
unchanged. Legacy helpers without a target context return no seeds.

Persist `searcher.selection` with the study checkpoint. Construct the recovery
searcher with that retained selection rather than querying newly arrived history.
`Study.load_checkpoint()` verifies the target identity, objective, selection,
cursor and base state before replacing live state. The compatibility
`WarmStartSearcher` supports explicit manual seeds and version-2 checkpoints;
older unbound checkpoints require explicit migration and are refused.

The prospective V12 version-2 contract uses six self-contained synthetic training
cases, independent mathematical reconstruction and immutable recovery evidence.
The historical empirical default/speedup claim is archived and remains
unestablished; these synthetic studies do not meet its real-history precondition.
Run `python -m examples.warm_start_tuning` for a retained development example.
Official finite acceptance requires the separate exact source/protocol freeze.

## Rank-weighted GP transfer

`RGPESearcher` first evaluates ranked eligible configurations on the target,
then uses an actual rank-weighted GP ensemble to propose sequential scalar EI
candidates. Declare target tuning and protected final roles before querying:

```python
from hponas import RGPESearcher

searcher = RGPESearcher.from_store(
    space, store, context=context, declaration=declaration,
    n_initial=4, seed=7, rank_samples=128, n_candidates=128,
)
study = Study(searcher, LocalExecutor(), objective, budget=16,
              study_name=context["study_id"], maximize=False, store=store,
              declaration=declaration)
```

The context's objective identity and direction must match the declaration.
Each completed source must have matching objective, model and protocol
semantics, plus raw declared tuning records that reconstruct its aggregate.
The usual history-cutoff, held-out-task and space checks also apply. Sources
without role proof are excluded. On the same data identity, any source tuning
exposure of target final score rows or groups excludes the source. Source final
measurements never enter the retained bundle. Caller-provided identities and
data access still rely on the trusted host and honest objective code.

Each task's objectives are standardized independently. Source weights estimate
minimum ordered-pair ranking loss on actual target points. Target ranking uses
leave-one-out predictions; equal minimum-loss ties split their weight equally.
The independent ensemble has mean `sum(w * mean)` and covariance
`sum(w**2 * covariance)`, mapped through the target's center and scale. This
fixed RBF-kernel variant uses lengthscale 0.25 and noise variance 1e-6 in
normalized units by default. It does not fit kernel hyperparameters or implement
noisy EI. The [algorithm reference](https://github.com/pytorch/botorch/blob/v0.8.5/tutorials/meta_learning_with_rgpe.ipynb)
uses a different first-index tie rule; this implementation's equal tie rule is
explicit and independently tested.

Support is limited to scalar sequential endpoint Studies with unconditional
continuous/ordinal coordinates: at most 20 coordinates, 16 sources,
128 valid points per source, 64 valid target points and 512 rank samples or
candidate points. Small ordinal domains are enumerated; a caller may supply
`candidates` for a finite domain. Duplicate proposals are excluded and finite
exhaustion is explicit. Failed target measurements remain in history and do not
fit a GP. With no eligible source, target-only fitting follows cold initial
sampling. Scheduling, concurrency, categorical/conditional spaces and vector
objectives are refused.

Checkpoints retain the complete source bundle, raw tuning proof, target
measurements, proposals and RNG. Restore with
`RGPESearcher.from_state(space, retained_searcher_state)` before
`Study.load_checkpoint()`; recovery never queries newly arrived sources.
Rehashed but inconsistent raw records, changed declarations, duplicate proposals
and replaced acknowledged measurements are refused before live state changes.
Hashes detect inconsistency; they do not authenticate an untrusted caller.

GAP-01/TRANSFER-DISPOSITIONS supplies development arithmetic and workflow
evidence. Current-source scientific qualification remains a separate master
stage. Mathematical correctness does not establish empirical transfer benefit.
