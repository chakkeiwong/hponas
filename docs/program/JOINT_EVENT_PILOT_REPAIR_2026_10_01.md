# A cheaper sufficient pilot bound within the existing rank protocol

This is STAT-03/ACTUAL-ALTERNATIVE in the current master. It changes only the
prospective pilot sizing calculation before any pilot exists. The confirmation
test, hypotheses, zero margins, nine components, Holm family alpha .05,
confirmation cap 20, .80 power target, .95 simultaneous planning confidence,
missingness handling and separate resource authorization remain unchanged.
The old bounded-mean sizing reports and implementation are retained as history.

The earlier sufficient rule estimates nine component means and two loss rates
separately, then combines conservative bounds. That is unnecessary when the
scientific entry itself requires all components. A single jointly sufficient
event can account for their dependence and the operational loss veto together.

## Derivation

Call a vector good for an entry if every retained component lower utility is at
least c = 84/125 = .672 and none of its planned studies is unresolved. This is a
planning event, not a new acceptance margin. The number comes from exact rational
arithmetic: it is the smallest thousandth c for which the registered uniform
mixture E on 18 copies of c and two copies of -1 is at least 40. E is monotone in
each utility because its integrand is a product of nonnegative factors
1+lambda*x for lambda in [0,1] and x in [-1,1].

For each fixed confirmation count n in 5..20, calculate the smallest integer
k_n such that both k_n >= n-floor(n/10) and E(k_n copies of c, n-k_n copies of
-1) >= 40. If none exists the count cannot use this sufficient event. At least
k_n good vectors imply every entry component p <= .025, sufficient for the
two-entry Holm family regardless of ordering. There are at most floor(n/10)
bad vectors, so even if every task is unresolved in every bad vector, the
per-arm unresolved fraction is at most 10%. No independence among components,
arms or tasks within a vector is assumed.

Under the already disclosed independent stationary-vector model, good indicators
are iid Bernoulli with an unknown probability pi for each entry. From m pilot
vectors and g good vectors, take the exact one-sided Clopper–Pearson lower bound
L at error .025. Bonferroni over the two entries supplies the same simultaneous
.95 planning confidence as before; no cross-entry independence is required.
Then entry success probability, conditional on adequate resources, is at least
P(Binomial(n,L) >= k_n). Select the smallest fixed n in 5..20 whose lower bound is
at least .80. If none exists, sizing is infeasible. All observed vectors count;
bad, missing, moderate and heterogeneous vectors cannot be removed.

The pilot is sizing-only and the confirmation is fresh. The same raw-process,
chronology, recipe, source and resource verifiers remain binding. Cost overrun
remains an actual veto; no statistical calculation promises resource adequacy.
The confidence statement is frequentist coverage of the planning rule, not a
posterior probability of truth or an unconditional guarantee of scientific PASS.

## Verification and tradeoff

`evidence/2026-10-01/scope-adoption/joint_event_sizing_review.py` compares every
good/bad-count combination for n=5..20 against exact rational polynomial
integration. It also enumerates binomial confidence failure probabilities over
999 probabilities at several pilot sizes. Maximum observed one-entry confidence
failure is .0249941, below .025. These computations cross-check the derivation;
the proof above establishes the stated assumptions and scope.

The ideal pilot first succeeds at 46 vectors per entry, versus 277/131 for the
old separate-mean rule. On three tasks and four/two arms this is 828 studies,
versus 4,110. No experiment outcome was used to choose this method.

This rule is not uniformly more powerful: many moderate vectors can have a
positive mean without ever meeting the joint .672 threshold. The benefit is a
substantially cheaper sufficient route when jointly strong vectors are common.
An ideal screen cannot establish that actual PPO meets it, and 46 vectors are
not an automatically authorized or recommended spend. Keep the pilot blocked
until the complete measured execution/resource plan and allocation are concrete.

The implementation will freeze this single rule before pilot outcomes; it will
not choose whichever of two confidence methods is favorable after observing
the pilot. Earlier proposal wording about simultaneous bounded confidence
limits remains satisfied by this exact joint-event confidence calculation.
