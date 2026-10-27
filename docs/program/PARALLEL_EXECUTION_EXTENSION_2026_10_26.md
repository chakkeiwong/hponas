# PAR-01: parallel CPU/GPU execution extension

Authorized 26 October 2026. This is a successor to the completed SCI-03 and
finite-local product, not a reinterpretation of V08 or T2-POP acceptance.
`CONSOLIDATED_MASTER_AUTHORITY.md` remains the sole master; `program.json` owns
execution state. One inspector/editor, repair/refresh at each boundary.

## Goal and non-negotiable semantics

Make every shipped tuning family usable with multiple CPU workers and available
GPUs. Distinguish concurrent trial evaluation, method-valid batch proposals,
independent study replicas, and parallel folds/seeds. Sequential adaptive methods
retain their ask/tell barriers: an independent-replica portfolio is available
without pretending to implement a new joint acquisition algorithm. BG-PBT must
parallelize independent population members and independent transfer/architecture
candidates, preserving deterministic generation and halving barriers.

CPU/GPU reservations are physical placement contracts, separate from scientific
update/fidelity budgets. A resource specification declares CPU cores, numerical
threads and whole GPU devices per worker; assignment records worker, attempt and
task identity. Reject infeasible requests before dispatch. CPU affinity and
numerical thread controls apply inside isolated workers. GPU visibility is set
before objective deserialization/device initialization; assigned logical devices
and physical IDs are visible to caller objectives. CPU-only tasks cannot silently
use CUDA. Whole-device exclusive leases are the first supported local contract.
Fractional GPU sharing and hard GPU-memory partitioning require explicit refusal
until separately implemented and tested. Multi-GPU trial placement does not
automatically implement DDP/model sharding inside caller training code.

Persistent spawn workers execute immutable inputs. The single coordinator owns
proposal order, admissions, durable observations and commits. Completion order
cannot reorder semantic updates. Never hold the population journal lock during
training. A reserved event identifies input hashes, target version and attempt;
commit is idempotent and rejects stale writers. Failed/uncertain work consumes
its reserved upper bound. Automatic retry is disabled by default. Resume cannot
replay committed work or silently reuse a failed allocation. Checkpoints are
CPU-portable; execution placement is distinct from mathematical model identity.

## Master stages and exit criteria

| Stage | Work | Required evidence |
|---|---|---|
| PAR-01/CONTRACT | Review source gaps, algorithm matrix, invariants and bounds | Reviewed contract; all public families mapped; predecessor preserved |
| PAR-01/RESOURCES | ResourceSpec, ExecutionContext and leases | Validation, infeasibility, duplicate/release and serialization tests |
| PAR-01/EXECUTORS | Persistent local spawn CPU/GPU workers; Ray context | Actual disjoint CPU workers, device assignment, timeout/crash cleanup; Ray control tests |
| PAR-01/STUDY | Public Study, repetitions, final evaluation and independent replicas | Ordered commits, known answers, protected final barrier, budget/recovery controls |
| PAR-01/POPULATION | Parallel PBT/PB2/BG-PBT and model-neutral adapter | Immutable snapshot compute, fenced commits, portable checkpoints, generation/halving equivalence |
| PAR-01/CONFORMANCE | Every shipped method on declared parallel route | Method matrix with executable test references; sequential/batch distinctions enforced |
| PAR-01/HARDWARE | Bounded CPU and available GPU validation | 1 versus multiple workers/devices, numerical agreement, failure injection and timings |
| PAR-01/DOCUMENTATION | Current manual and executable examples | Built LaTeX, actual API examples, result/limitation ledger |
| PAR-01/AUDIT | Terminal source/test/evidence/requirement reconstruction | All stages closed with current-source evidence; no inherited parallel claim |

The stages are sequential. The final audit depends on every preceding stage.
At a boundary retain failed evidence, fix demonstrated defects, bind the next
bounded roster and continue; no human scientific acceptance gate. Historical
GAP completion remains historical and is not modified to certify this source.

## Algorithm matrix to implement and verify

* Random/Sobol/TPE: bounded independent proposals and ordered observations.
* GP and vector GP: existing joint batch/pending contract; no new acquisition.
* Multi-objective random/NSGA-II, CMA-ES: existing generation semantics.
* ASHA/PASHA/PriorBand: existing promotion/report barriers; independent jobs.
* DEHB, trust-region, cost-GP, robust-GP, RGPE: preserve any single-pending
  restriction; parallel independent study replicas and independent repetitions.
* PBT/PB2-Mix/BG-PBT: independent members and transfer candidates within barriers.
* Model-neutral population adapter: caller checkpoint/restore in isolated workers.

Do not silently turn a sequential algorithm into a batch heuristic. Any missing
route is an open implementation gap and prevents completion of this extension.

## Objective validation and resource allocation

Use only repository-owned deterministic scalar/vector/constrained analytic
fixtures, finite fidelity, finite MDP, tiny neural models and device-aware tensor
work. No sibling imports/data/services and no real-bank effectiveness claim.
Compare equal worker-count schedules under adversarial completion orders;
compare serial and parallel execution of the same frozen batch (different batch
sizes can legitimately choose different adaptive configurations). Check event
identity, selection, model outputs, lineage, budgets and durable recovery.
Inject crash, timeout, cancellation, stale commit, failure before/after compute
and CUDA OOM handling. Retain explicit unavailable hardware outcomes.

CPU exact fixtures use exact equality; floating CPU/CUDA fixtures declare
dtype-specific absolute/relative tolerances before execution (float64 1e-9/1e-7;
float32 1e-5/1e-4). Do not change tolerances after observing a failure.
Speedup T1/TW and efficiency T1/(W*TW) are measurements, not scientific superiority
or automatic acceptance thresholds. Synchronize CUDA before timing. Record
worker overlap, device identity, memory and orchestration overhead.

Fixed development operations: at most 4 CPU cores, one numerical thread per
worker, 300 seconds per test group, 8 GiB owned RSS; hardware stage at most 2
available GPUs, 2 workers, 600 seconds, tiny tensors/models, no downloads.
Final regression groups keep their existing bounds. Device reservation cannot
exclude unrelated OS processes: detect/report existing use and avoid busy GPUs.
No service deployment, separate-machine test, broad campaign, git mutation or
global allow-rule change is authorized by these operations. Prepare exact
fixed entrypoints and concrete manifests; group escalation only if required
by the managed layer. Source changes need new evidence; old PASS stays old.

## Design review

Reviewed against current executor, Study, resource budget, population journal,
BG-PBT controller, adapter and capability implementations. Main failure modes:
threaded CUDA environment races; one-inflight budget assumptions; journal locks
covering computation; eager CUDA initialization; stale concurrent population
writers; completion-order-dependent optimizer state; nesting worker pools;
hidden retries; mocked GPU checks mistaken for multi-GPU execution.
The staged design addresses each at its owning layer and leaves hardware and
terminal audit after integration. The finite baseline is preserved as a hashed
predecessor. This review approves implementation, not a result or completion.
