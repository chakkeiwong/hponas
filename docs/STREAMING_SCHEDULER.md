# ASHA reporting and continuation

`ASHAScheduler(ASHAConfig(...))` uses the Syne Tune 0.13.0 promotion rule. A rung needs two observations before any promotion. The linear `1 / eta` quantile determines eligibility; ties qualify. `promote()` dispatches one candidate, starting at the highest eligible rung. Call it again when another worker slot is available. Ineligible candidates stay paused and can qualify after later results arrive.

To replay the former bootstrap/quota behavior, select `promotion_policy="legacy_bootstrap"` explicitly. Unversioned ASHA checkpoints require that policy. Reference and compatibility checkpoints cannot be silently interchanged. Compatibility includes the former live-value median heuristic and does not establish reference ASHA or completed-trial median conformance.

An objective opts into streaming by declaring `reporter`. The local thread, local timeout-process, and Ray executors all exchange decisions while the call is running:

```python
def train(config, fidelity, resume_from, checkpoint, reporter):
    state = checkpoint or {"x": config["x"], "step": 0}
    for step in range(int(resume_from) + 1, int(fidelity) + 1):
        # Replace this calculation with one training step and its metric.
        value = (state["x"] - 0.25) ** 2 + 1 / step
        state = {**state, "step": step}
        reporter(step, value, cost=step - resume_from, checkpoint=state)
    return {"value": value, "cost": fidelity - resume_from, "checkpoint": state}
```

`reporter` takes an absolute resource step, a finite scalar metric, cumulative cost **for this evaluation call**, and optional checkpoint state. Steps and cost must not decrease. Duplicate step/value reports are idempotent; conflicting duplicates fail. A pause, prune, or cancellation interrupts the objective, so save continuation state before reporting. Do not catch its control exception. A final returned metric must agree with a report at the same endpoint, and returned cost cannot discard already reported work.

Checkpoints must be JSON state or durable references accessible to every worker that may resume the trial. Returning a model object is unsupported. Root trial identity remains the same across promotions; each evaluation has a separate `trial_id` and `parent_trial_id`.

`Study(..., continuation="resume")` carries checkpoint state and the parent's fidelity into promoted calls. A promoted resumed call must accept `checkpoint` and `resume_from`, and must have a checkpoint. `continuation="restart"` is the default: each call starts at zero and pays for the repeated prefix. The repeated prefix cannot supply new scheduler evidence or cause another pause at an already promoted rung. The study ledger records the continuation mode.

Median pruning is opt-in with an explicit grid, for example:

```python
ASHAConfig(r_min=1, r_max=9, median_stopping=True,
           report_grid=tuple(range(1, 10)), median_min_completed=5)
```

At a grid step, compare the current arithmetic running mean over the grid prefix with the median of the same prefix means from completed full-training trials. Five usable completed references are required by default. Paused, running, failed, cancelled, and pruned trials are excluded. A missing grid point makes that prefix unavailable; it is not interpolated. An endpoint-only objective can still run, but it provides no streamed median history. The survey's always-on default remains a separate release decision.

A completed evaluation at a lower rung is a paused training trial. `Result.is_valid()` permits a finite paused rung observation for searcher updates; `Study` selects an incumbent only from completed evaluations at the scheduler's required final fidelity. If no such result exists, `run()` raises `IncompleteStudyError`. Its `.result` contains the history, costs, `status="incomplete"`, and reason. The checkpoint and Store retain that outcome, with no low-fidelity incumbent substituted.

`budget` counts new configurations. `compute_budget_seconds` separately stops dispatch and cancels cooperative training when the sum of measured evaluation elapsed seconds reaches its limit. It is checked at reports and completions, so an in-flight reporting interval or endpoint-only call can overshoot. Use executor deadlines to bound non-reporting calls. This is elapsed evaluation accounting, not allocation-attributed GPU time and not a claim of hard real-time enforcement. Experiment protocols must separately specify their resource measure and allowed overshoot.

Worker retries and restarted promotions charge repeated work. After an interrupted study, acknowledged elapsed time and reported cost are retained; unreported work since the last durable report cannot be reconstructed. Such recovered evaluations explicitly carry `execution.accounting="lower_bound_after_interruption"`. They cannot establish an exact compute-saving claim. `Study.cancel_trial(trial_id)` requests cooperative cancellation by evaluation or root identity.

Study checkpoints use schema 3 and progress/terminal events use schema 1. Schema 2 endpoint ledgers can still be loaded under their explicit scheduler policy. The event log records progress, effective controls, completion, cancellation, and promotion context; replay recomputes scheduler decisions in recorded order. It is evidence of reproducibility for that recorded execution, not statistical or release acceptance.

The maintained `workloads.streaming_quadratic.StreamingQuadratic` provides a
self-contained training example with a mathematically known answer. It executes
actual rotated-quadratic gradient updates, reports each integer iteration and
retains local physical-work traces. The checkpoint contains the configuration,
completed iterations and numerical state. Checkpoint validation does not
re-execute preceding training updates. A resumed sequence of fidelities
1, 2, 4, 8 uses eight gradient updates; restarting each endpoint uses fifteen.

Run the bounded end-to-end example from the checkout:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m examples.multifidelity_tuning --output-dir /tmp/mf
```

It retains fourteen cases: full evaluation, three proposal orders crossed with
resume/restart and median off/on, and an interrupted resumed case. The separate
`validation.multifidelity_reference` reconstructs rational trajectories,
completed-reference median decisions, promotion quantiles and physical charges
from the raw traces. Order can change which late improver reaches the endpoint;
restarting can cost more updates than full evaluation. Those outcomes remain
adverse fixtures, not V06 acceptance or justification for default activation.
Update counts are not wall time, GPU time or a hardware cost proxy. The complete
local physical trace can count an injected repeated update; Study still marks
unobservable work after a crash as a lower bound.
