# Joint GP proposals and pending evaluations

Public `GPSearcher.suggest_batch(q)` proposes up to eight locations together.
`Study` uses it when more than one dispatch slot is available and the searcher
declares joint batch support. It registers the whole returned set and saves
pending configurations before dispatch. The existing single-proposal method
remains available. Initial design uses distinct random locations; after enough
valid observations the acquisition is a joint BoTorch qLogExpectedImprovement.

For a fixed fitted posterior, current best value b, pending locations P and
new locations X, the ideal unsmoothed acquisition is

\[
 U(X;P)=\mathbb{E}[(\max_{z\in X\cup P} f(z)-b)_+].
\]

BoTorch concatenates `X_pending` with X and samples the joint posterior,
including cross-correlations. It estimates a smoothed log version of U.
Repeated optimization of individual EI values does not optimize this set
function: two individually strong correlated points can be worse as a pair
than a strong point and a less correlated alternative.

The pending interpretation follows the identity

\[
 U(X;P)=U(\varnothing;P)+
 \mathbb{E}_{Z=f(P)}\left[
   \mathbb{E}\left[(\max_{x\in X}f(x)-\max(b,\max Z))_+\mid Z\right]
 \right].
\]

The first term is constant in X. Thus joint pending integration has the same
ideal maximizers as averaging conditional improvement over latent pending
values under that fixed posterior. This implementation does **not** explicitly
refit fantasy models, update GP hyperparameters for imaginary observations,
condition on noisy future observations, or optimize an adaptive policy that
chooses X after observing P. Monte Carlo and smooth-max approximations also
mean the computed acquisition is not an exact expected-value certificate.

For small wholly discrete domains, the method excludes pending locations,
prefers previously untried configurations, and evaluates all unordered q-point
sets within a 4,096-set enumeration bound. A short untried pool can return
fewer than q points. When every configuration was observed, replication is
allowed, but never a duplicate within one batch or of a pending location.
The domain itself also retains the 4,096-configuration enumeration bound.
For unconditional continuous spaces, one `optimize_acqf(q=q)` call searches
the joint numerical acquisition with the existing restart/raw-sample settings.
This is local numerical optimization, not a global-optimum proof. Rounded
large/mixed-domain q>1 acquisition is explicitly unsupported. Invalid duplicate
optimizer outputs are refused. Initial random proposal search is bounded at
1,024 draws and reports pending/no-location rather than looping forever.

GP snapshots retain the RNG, proposal records, registered locations and
ordered observation history. Pending IDs must reconstruct from the trial and
observation ledgers. Study commits observations in dispatch order; recovery
reuses committed proposals and skips committed results. A direct searcher
caller must register returned Configs in its trial map before requesting a
subsequent set; Study performs that step. The proposal trace contains search
acquisition values, never protected final measurements.

Warm-start wrappers keep single proposals so their seed queues remain ordered;
they do not inherit a joint-batch claim merely by wrapping GP. Robust GP keeps
its sequential capability. Random, prior and other searchers retain their
own proposal semantics. This feature does not promote a method default or
transfer the retained baseline's scientific qualification to changed code.

## Multi-objective batches

`MultiObjectiveBayesSearcher.suggest_batch(q)` now supports one through eight
joint locations for qLogNEHVI and augmented Chebyshev/qLogEI. Public vector
Study uses the same durable batch registration. A seeded pool of legal,
nonpending continuous/ordinal configurations is selected, then every unordered
q-set in that pool is evaluated jointly. The pool is shortened before scoring
when necessary to keep at most 4,096 sets. The trace records actual q, pool
size, number of sets, pending count and selected configurations. This is a
bounded candidate-pool optimum, not global optimization over a continuous domain.

Completed points may be replicated; duplicates within a batch or pending
locations are refused. A smaller available pool returns a shorter batch;
an all-pending finite domain waits without advancing the RNG. Acquisition
failure restores proposal RNG/trace state. New snapshots use
`botorch_multi_objective_v2`; old v1 snapshots require their retained source.
Scalar GP's earlier checkpoint contract is unchanged. GAP-01/MO-BATCH
implementation, current-source qualification and final audit status are recorded
in the [master](../CONSOLIDATED_MASTER_AUTHORITY.md) and
[atomic gap ledger](program/gap_closure.json). The
[guidance repair record](program/evidence/2026-10-18/gap-guidance-repair-01/plan-review.md)
retains the replaced status sentence.
