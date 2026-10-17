# Serial DEHB

`DEHBController` minimizes a scalar objective using differential evolution and
Hyperband. Run `python -m examples.dehb_tuning` from this checkout for a small
gradient-descent example with an exact spectral answer and JSON recovery.

Create a controller with a native `SearchSpace`, call `ask()`, evaluate the
returned `Trial` through `LocalExecutor`, then call `tell(result)`. One trial
may be outstanding. `ask()` repeats that identity until a finite completed
report commits it. Exact duplicate reports are idempotent; conflicting reports
are refused. Failed evaluations remain pending and require explicit caller
handling. The caller accounts for every physical attempt, including failures
and retries; controller history contains completed reports only.

Every assigned fidelity starts training from the beginning. Promotions reuse
configurations, not training checkpoints. `best()` selects full-fidelity results
by default, avoiding comparisons between incompatible training budgets.

Persist `state_dict()` with `hponas.persistence.atomic_json` and load it into a
controller with the identical space and options. Recovery reconstructs the
seeded algorithm from its transcript without rerunning objectives. Reissuing
pending work does not guarantee exactly-once physical execution. Transcript
storage and restore time grow with completed evaluations; this serial local
controller is not a distributed service.

The owned rand/1/binomial method follows DEHB v0.1.2 commit
`58f9fb9045e63530692adc6306fc297e318f11f2`, including random boundary repair.
The upstream Apache-2.0 notice is packaged in `licenses/DEHB-Apache-2.0.txt`.
The product does not import upstream DEHB, Dask or ConfigSpace. Mixed,
conditional and transformed coordinates use the native HPO-NAS encoder;
ConfigSpace equivalence is not claimed. Other mutation strategies and parallel
asynchronous execution are unsupported. Limits are 64 coordinates, ten rungs
and 4,096 population members. Fidelity is numeric; integer training workloads
must choose integral rungs.

Finite V07 conformance checks fixed method trajectories, known-answer training,
work accounting and recovery. It does not establish optimizer superiority,
RL defaults or integrated-release readiness.
