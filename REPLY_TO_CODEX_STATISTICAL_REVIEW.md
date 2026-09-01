# Response: Statistical Protocol Review

**Date:** 2026-09-01
**Review:** [RESPONSE_TO_CODEX_STATISTICAL_REVIEW.md](RESPONSE_TO_CODEX_STATISTICAL_REVIEW.md) — verdict RED
**Response author:** Implementation team
**Status:** Findings accepted; repairs implemented and committed. Re-review requested.

---

## Executive response

We accept the RED verdict. The review is correct that the protocols were not
executable as written, and correct on a point that matters more than any single
finding: several rules in the chapter contradicted corrections we had already
accepted in writing. We had treated "the corrections are agreed" as equivalent to
"the corrections are in force," and nothing in the process distinguished the two.

Repairs are implemented across three commits and all findings are addressed. We are
not claiming the statistical reviewer gate is closed — that requires this re-review
plus the pilot report, and the sign-off level itself is still an open decision (D5
below).

**One correction to the review**, offered because it affects how V08 should be read
rather than to contest the finding: F3 states the 3-repetition exception "cannot
produce pass, while hold is allowed to complete the tier." The chapter already said
this deliberately — it called the tripwire "not promotion evidence" and reserved pass
for a full campaign. The defect was not that pass was unreachable by design; it was
that the design's states had no operational triggers (no tie rule, no minimum loss
margin, no missing-run rule) and that hold had no owner, expiry, or funding. We have
fixed those. The asymmetry itself we have kept, and made its cost explicit by
reporting the simulated false-demotion rate.

---

## Root cause of F1

The per-entry corrections in `RESPONSE_TO_CODEX_REVIEW.md` (lines 257–269) were
specific and correct. They were never mechanically compared against the chapter, so
the chapter kept the superseded text and the divergence survived until this review.

Auditing for it, we found the drift was broader than F1 listed: **V01 was a fifth
instance**, still specifying the 0.5% tolerance band that the accepted corrections had
replaced with distributional regression. F1 named V09, V10, and V13. A review found
four; a mechanical check finds all of them, every time, which is the actual lesson.

The repair is therefore structural, not editorial. `validation/protocols.json` is now
the authority for every decision-bearing rule, and `tools/check_protocols.py` fails
the build when the chapter, the register, and the program disagree. Both were
negative-tested against injected defects — including reintroducing the V09 overlap
rule and the V10 single-seed design — and caught all of them.

---

## Findings

### F1 — Chapter drifted from accepted corrections. **Repaired.**

| Entry | Was | Now |
|---|---|---|
| V01 | 0.5% tolerance band (not in F1; found while auditing) | Two-sample distributional comparison at shared seeds |
| V09 | Demote if the interval overlaps Chebyshev's | Paired test on the difference; reference point and normalization frozen from registry bounds before data |
| V10 | Spearman rho ≥ 0.6, 100 configs at one fixed seed | Upper bound on false-cull probability ≤ 0.05 and lower bound on top-10 recall ≥ 0.90, across 5 seeds and several tasks; rho retained as descriptive |
| V13 | Visual trace inspection; agreement within one standard error | Automated mode diagnostics as a preregistered branch; SBC fixtures; simultaneous MCSE-aware bands |

On V13's agreement check specifically, the review called it weak; it is worse than
weak. A one-standard-error band is roughly a 68% interval, so a *correct* sampler
failed it about a third of the time, and the criterion treated the reference as exact
when the reference is a finite sample with its own Monte Carlo error.

### F2 — Confirmatory error control and sample size not reproducible. **Repaired.**

The chapter's reasoning was "the primary endpoint is judged at α = 0.05 uncorrected,
because there is one of it." There is one *per entry*; a gate decides six at once.
The review's arithmetic (0.265 for six, 0.537 for fifteen) is the cost of that
inference.

The family is now the gate, with Holm–Bonferroni over decision-bearing tests only.
We chose per-gate over a global family because gates are separate decisions taken at
different times on different data with different release consequences, and a family
stretched across thirty weeks would cost the tier-0 floor tests real power for no
inferential gain. Hard vetoes and reproduction checks are excluded and consume no
alpha: they decide on deterministic criteria, not rejected nulls.

Power is now reproducible: simulation under each entry's own hierarchy rather than a
closed form that does not describe a cluster-level paired difference; minimum pilot
raised from 3 to 5; sizing against the upper confidence bound on pilot variance so
pilot noise inflates rather than shrinks the sample; pilot data excluded from the
confirmatory estimate; declared maximum sample per entry.

### F3 — V06 and V08 undecidable from the stated metrics. **Repaired.**

V06's primary cost estimand is billed resource-seconds, with active accelerator
time, CPU, wall-clock, and queue wait as separate secondary columns. Queue wait is
reported in seconds and never converted into accelerator-seconds. We chose billed
resource-seconds because the claim is about what a user pays: active accelerator time
understates a wasteful schedule, wall-clock charges an arm for unrelated contention.
Pass now requires quality non-inferiority **and** a cost upper bound, as an
intersection-union rule.

V08's states now have triggers: ordering statistic (mean range-normalized difference
against the worse comparator), tie band (±0.02), minimum loss margin (0.10, twice the
decision margin), missing-run rule, and a named home regime (16 workers; 4 on the
lower side). Implementation failure is a distinct state from method loss. Hold
requires a named owner, dated expiry, and funded follow-up committed when the hold is
entered; it ships opt-in with no default dispatch and auto-demotes on expiry. The
V07 tie fallback is declared, since V08's demotion path previously resolved to
another entry's undefined outcome.

---

## The eight requested items

| Item | Was | Now |
|---|---|---|
| 1. Margins | Symmetric containment (equivalence) on a percentage scale | One-sided non-inferiority, direction-normalized, range-normalized against bounds declared before data. V11 split: V11a superiority under a good prior, V11b non-inferiority under a wrong one |
| 2. Power | Pilot → 80% power, nothing else specified | Simulation under the entry's hierarchy; min pilot 5; conservative UCB on pilot variance; pilot data excluded; 0.9 target for V04-T1 and V08 |
| 3. Resampling | Runs resampled within tasks | Paired cluster bootstrap on complete study blocks; trials never the unit; pairing frozen before data; single-cluster entries limited to pinned-task claims |
| 4. Tasks | Role separation only | Selection algorithm and candidate set committed by hash before implementation freeze; per-task exposure history; no reuse across claims |
| 5. Multiplicity | Uncorrected primaries | Per-gate Holm–Bonferroni; intersection-union declared where a method must beat several comparators; summary functional fixed before data for curve-based decisions |
| 6. V06 cost | Queue folded into accelerator-seconds | Billed resource-seconds primary; four secondary columns; deterministic attribution; bootstrap interval on the ratio |
| 7. Artifacts | "Signed" and "immutable" undefined | Named signature scheme over canonical JSON, key ownership and rotation, full lock contents, object store for large artifacts, enforced pre-run verification order |
| 8. V08 | States named, triggers absent | Triggers, tie rule, missing-run rule, minimum loss margin, home regime, implementation-fail state, hold with owner/expiry/funding and auto-demotion |

On item 1's percentage-scale objection: we adopted range normalization against
pre-declared bounds. RL return is routinely zero or negative, so a percentage is
undefined or unstable there, and a denominator estimated mid-campaign is a threshold
that moves with the data.

**Structural changes:** V04 → V04-T0/V04-T1, V11 → V11a/V11b, V15 → V15a/V15b. V11
could not be tested as one entry: it bundled a superiority and a non-inferiority
claim under a single margin.

---

## Your minimum amendments

| # | Amendment | Status |
|---|---|---|
| 1 | Reconcile chapter with accepted V09/V10/V13 commitments; regenerate register | **Done** — plus V01, found while auditing |
| 2 | One machine-readable protocol record per entry | **Done** — `validation/protocols.json`, 18 entries, completeness enforced by CI |
| 3 | Freeze task and seed registries via signed pre-run manifest | **Specified, not built** — the tooling is Tier 0 work |
| 4 | Paired cluster resampling; pilot simulations for coverage and power | **Specified, not run** — the pilot report is the remaining evidence gap |
| 5 | Freeze hypervolume normalization and V10/V13 thresholds | **Done** — in the register, frozen from registry bounds |
| 6 | Artifact signing, key verification, lock, retention, versioning | **Specified, not built** — Tier 0 |
| 7 | Resolve V08 state machine, funding, and hold semantics | **Done** |
| 8 | Obtain the intended sign-off level | **Open — D5**, see below |

Amendments 3, 4, and 6 are specified but unbuilt. We are not treating specification
as completion: they gate campaign execution, not implementation, and the pilot report
under amendment 4 is the substantive remaining evidence gap.

---

## Decisions requiring sign-off

Four are recorded as PROPOSED in `policy.open_decisions` and one is OPEN. They are
judgment calls, not derivable from the review:

- **D1 — family scope:** per-gate (chosen) vs global vs hierarchical gatekeeping.
- **D2 — power targets:** 0.8 default with 0.9 for V04-T1 and V08 (chosen) vs 0.9
  throughout. Rationale: power protects against false demotion, and those two carry
  the sunk build cost that makes a false demotion expensive.
- **D3 — V08 hold:** time-limited opt-in with auto-demotion (chosen) vs hold blocks
  the beta gate.
- **D4 — V06 cost estimand:** billed resource-seconds (chosen).
- **D5 — sign-off level:** **OPEN.** Either this re-review plus validation-lead
  self-certification, or that plus a paid human statistician. Your amendment 8 is
  right that this review is not credentialed external certification, and we are not
  logging it as one.

---

## What we are asking for

1. **Re-review** of `validation/protocols.json` and the amended chapter, particularly
   the D1 family-scope choice, the V10 safety bounds, and whether V08's tripwire is
   now honestly bounded.
2. **A view on D5.** If any finding here looks like it needed credentialed review
   rather than engineering review, say so and we will budget the statistician.

Tier 0 implementation continues as engineering work, per your decision paragraph. No
campaign budget will be spent against these protocols until the re-review, the pilot
report, and D5 are all resolved.

---

## Status note

You flagged that the memo said Tier 0 implementation was underway while the progress
tracker said Tier 0 was pending approval. The tracker was right and the memo was
wrong. Tier 0 has not started; R1 is complete and Tier 0 is blocked on program
approval. Corrected here and in the tracker.

---

**Commits:** `8c39fbe` (register and validator), `158b06e` (chapter amendments and
drift tripwire). Survey builds clean at 118 pages, 0 undefined references.
