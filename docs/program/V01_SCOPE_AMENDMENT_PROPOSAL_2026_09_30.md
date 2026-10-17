# Proposed V01 reference and claim boundary

This is **STAT-03/F / VAL-01 within the master**. It is a concrete proposal,
not an amendment to the active protocol and not a scientific acceptance.

The active V01 estimand is “Equality in distribution between our wrapper and
the vendor reference on tabular benchmarks at shared seeds and matched budget.”
Its finite two-sample KS procedure cannot establish that equality. If wrappers
differ on one seed in a thousand, 30 independently sampled seeds miss every
disagreement with probability `(999/1000)^30`, approximately 97.04%. Even this
probability calculation does not apply to our deliberately fixed engineering
seeds. No choice of a human acceptance label changes the logical gap.

Equality in law could instead follow from a complete transition correspondence:
related initial states and coupled random streams, preservation under every
reachable event, and equality of all observables. That proof is not presently
available for the entire vendor inventory. PASHA also has a concrete reference
conflict: its pinned vendor implementation can count one unordered pair twice,
producing epsilon 9.2 or 10 for the same observations under different set
iteration orders. The implemented unordered-pair correction is explicitly a
reference adapter. Tests against it do not prove unmodified vendor parity.

The recommended replacement claim is:

> Every shipped wrapper and scheduler conforms to its explicitly named reference
> transition law on the prospectively frozen tabular and event corpus, under the
> pinned dependencies, numerical execution settings and random streams.

The proposed estimand is equality of the observed configuration-cell, decision,
policy-selection and score traces **on that finite corpus**. The acceptance
criterion is zero discrepancies and complete required evidence. An unresolved
source cell or missing execution remains INCONCLUSIVE; no task, seed or cell is
replaced after observing results. The corpus and complete component inventory
must be frozen before the corresponding acceptance execution. Existing
engineering traces remain historical preparation, including all missing cells.

Reference identities must be exact: pinned NumPy/SciPy/Optuna/BoTorch procedures
for their declared searchers; pinned ASHA promotion; the adopted completed-run
median specification; PASHA's pinned promotion law plus the disclosed
deterministic unordered-pair tolerance correction. The latter must never be
described as the unmodified vendor. Original and adapted sources and their
counterexamples remain bound evidence.

This proposal changes the scope of V01 from a global distributional assertion
to an objectively checkable finite conformance assertion. It adds no numerical
success tolerance, performance claim or spending authority. Such a scope change
requires authorization under the master's requirement to preserve adopted claim
identities; approving it would authorize the target contract, **not decide its
result**. If the global claim is retained, V01 stays unresolved until the full
transition proof and exact vendor/reference conflict are resolved. The agent
does not invent a PASS in either route.

After authorization, the agent will version the protocol/candidate, bind the
reference inventory and fresh corpus, implement the final acceptance adapter,
run its adversarial checks, and continue the phase repair/refresh sequence.
V02's final freeze will also bind the existing 10,000-case stratum, eight raw
integration scenarios and mandatory SPEC-02/SPEC-03 conformance obligations;
none establishes correctness for every possible asynchronous execution.
