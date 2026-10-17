# Ranked warm starts

Warm starts remain opt-in. The implementation transfers candidate configurations,
then evaluates them on the new task. It never imports old objective values as
new observations. It does not implement RGPE or establish a V12 speedup.

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
              study_name="new-study", maximize=False, store=store)
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
