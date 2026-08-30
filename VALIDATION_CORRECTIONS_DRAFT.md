# LaTeX Validation Chapter Corrections
**File:** hpo-survey/sections/16-validation.tex  
**Status:** DRAFT corrections ready for review  
**Statistical reviewer:** TBD (needs assignment)

---

## Summary of changes

This document contains all statistical corrections required by the Codex technical review. Each correction fixes a specific methodological error:

1. **Non-inferiority replaces CI-overlap** — "Within noise" redefined using equivalence margins
2. **Power analysis added** — Repetition count justified by pilot variance + minimum detectable effect
3. **Sampling hierarchy specified** — Hierarchical bootstrap, paired designs where valid
4. **Development vs held-out tasks** — Prevents in-sample overfitting to validation set
5. **Multiplicity control** — Family-wise error rate control for multiple comparisons
6. **Actual cost accounting** — Real accelerator-seconds, not just idealized equivalents
7. **Preregistration artifacts** — Immutable manifests with checksums, signed reports

---

## Correction 1: Non-inferiority for V06 and V11

**Location:** Lines 165-169

**Current text (WRONG):**
```latex
\textbf{``Within noise'' (V06, V11):} The 95\% bootstrap confidence
interval of the difference in means overlaps zero. Bootstrap by
resampling tuning runs with replacement, 10,000 iterations,
empirical percentiles. A result within noise is never used to claim
one method beats another; it is evidence of a tie.
```

**Problem:** CI overlapping zero only means "difference not detected," not "methods equivalent"

**Corrected text:**
```latex
\textbf{``Within noise'' (V06, V11):} The 95\% bootstrap confidence
interval of the difference in means lies entirely within the 
preregistered non-inferiority margin $[-\delta, +\delta]$. For V06, 
$\delta = 5\%$ of the full-fidelity baseline's final quality, 
representing the minimum practically important difference. For V11, 
$\delta = 10\%$ of the no-prior baseline's performance. Bootstrap by
resampling tuning runs with replacement, 10,000 iterations, taking
empirical percentiles. A confidence interval that overlaps zero but 
extends beyond the margin is recorded as inconclusive, not as evidence 
of equivalence. Only when the entire interval falls within 
$[-\delta, +\delta]$ is the claim of equivalence supported.
```

---

## Correction 2: Power and repetition policy

**Location:** Lines 127-139 in "The statistical protocol" section

**Current text (INCOMPLETE):**
```latex
Every layer-two comparison follows one protocol, copied from the
discipline of \citet{eimer2023hyperparameters} and from this
document's own warnings. Fixed tuning seeds and disjoint test seeds.
Matched budgets counted in full-run equivalents, with the tuner's
own overhead included in the bill. At least ten repetitions of every
comparison, reported as performance-over-budget curves with
uncertainty bands, never as single numbers.
```

**Problem:** No justification for "ten repetitions," no power analysis, no inconclusive state

**Corrected text:**
```latex
Every layer-two comparison follows one protocol, copied from the
discipline of \citet{eimer2023hyperparameters} and from this
document's own warnings. Fixed tuning seeds and disjoint test seeds.
Matched budgets counted in full-run equivalents, with the tuner's
own overhead included in the bill. Repetition counts are set by 
pilot variance estimates and the preregistered minimum detectable 
effect: a pilot campaign estimates the between-run variance, and the 
sample size is computed to achieve 80\% power at the decision margin. 
The protocol may specify a maximum sample size for cost control; if 
the maximum is reached without meeting the decision threshold, the 
result is recorded as ``inconclusive at budgeted precision'' rather 
than forced to a binary claim. All results are reported as 
performance-over-budget curves with uncertainty bands, never as 
single numbers. Pilot variance estimates are recorded before full 
campaigns begin and are not updated during execution.
```

**Add after this paragraph:**
```latex
The ten-repetition floor mentioned in earlier sections is a planning 
heuristic, not a replacement for power analysis. Where pilot data 
supports fewer repetitions (low variance, large effect), the protocol 
documents the justification. Where pilot data demands more (high 
variance, small margin), the budget is increased or the claim 
softened accordingly.
```

---

## Correction 3: Sampling hierarchy

**Location:** NEW SECTION after line 199 (after "Register shorthand resolved")

**Add:**
```latex
\subsection{Sampling levels and paired designs}

HPO comparisons have multiple sampling levels: optimizer random seeds 
(which tuning run), workload training seeds (which neural network 
initialization or environment instance), evaluation seeds (which test 
episodes), task selection (which benchmark), and configuration draws 
(which candidate hyperparameters are tried). Analysis must respect 
this hierarchy to avoid pseudoreplication—treating dependent samples 
as independent inflates claimed precision and produces unreliable 
decisions.

Where valid, the protocol uses paired designs: common random seeds 
across methods being compared, common task and environment instances, 
and common baseline configurations drawn once and evaluated by all 
methods. This reduces between-method variance and increases power 
without requiring larger sample sizes.

Uncertainty is computed via hierarchical bootstrap: resample complete 
tuning runs (the top-level unit) with replacement, compute the 
statistic of interest on each bootstrap sample, and take empirical 
percentiles over 10,000 iterations. When runs span multiple tasks, 
resample runs-within-tasks to preserve the task-level structure. This 
approach naturally propagates uncertainty from all sampling levels 
without requiring parametric assumptions about the data distribution.
```

---

## Correction 4: Development vs held-out tasks

**Location:** NEW SECTION after sampling hierarchy section

**Add:**
```latex
\subsection{Development and acceptance tasks}

Each workload family has two disjoint task sets: development tasks 
used during implementation, debugging, and informal testing, plus 
held-out acceptance tasks used only in formal gate campaigns. 
Development tasks are specified in week 1 of Tier 0 and documented 
in the validation manifest; implementers may run them freely to guide 
tuning and debugging. Acceptance tasks are selected by an engineer 
not involved in the implementation, revealed only at gate time, and 
recorded in the immutable gate manifest alongside their data 
checksums.

This separation bounds in-sample overfitting: a method that performs 
well on development tasks but fails on held-out acceptance tasks has 
overfit to the validation set itself. Both development and acceptance 
performance are reported; promotion decisions weigh acceptance 
results more heavily.

Task rotation follows a versioned process: after a full tier 
completes and its gate results are recorded, new tasks enter the 
development set, and a subset of old development tasks may migrate 
to acceptance in the next tier. The rotation is documented in the 
task registry with version numbers and dates, making task-selection 
bias auditable.
```

---

## Correction 5: Multiplicity control

**Location:** NEW SECTION after development/acceptance tasks section

**Add:**
```latex
\subsection{Multiple comparisons and endpoints}

Several validation entries test multiple hypotheses: V04 compares 
multiple searchers across tasks and budget points; V09 tests 
multiple objectives and comparators; V13 examines many posterior 
marginals. When multiple tests are conducted and ranking claims are 
made, the protocol controls for multiplicity to avoid false 
discoveries.

Each entry predeclares one primary endpoint—the single comparison 
the tier's completion depends on—and labels remaining comparisons as 
secondary or exploratory. For primary endpoints, the decision 
threshold remains at $\alpha = 0.05$ with no correction. For 
secondary endpoints that inform ranking claims, family-wise error 
rate is controlled at $\alpha = 0.05$ via the Holm-Bonferroni 
stepdown procedure \citep{holm1979simple}. Purely descriptive 
comparisons with no release decision attached (e.g., reporting that 
method A finished ahead of method B without claiming A should be 
preferred) require no multiplicity correction.

The primary endpoint for each entry is documented in its protocol 
before the campaign begins. V04's primary endpoint, for example, is 
whether the tier-0 GP+qLogEI beats the log+Sobol floor on the 
acceptance task; comparisons between GP variants or across 
development tasks are secondary.
```

---

## Correction 6: Actual cost accounting for V06

**Location:** Lines 171-175

**Current text (IDEALIZED):**
```latex
\textbf{``A fraction of compute'' (V06):} Early stopping reaches the
same final quality at no more than one-third the total compute of
full-fidelity search. Compute is measured in full-run equivalents,
charging partial runs proportionally. V06 passes only if ASHA
delivers the factor-of-three savings the chapter promises.
```

**Problem:** Ignores startup, evaluation, checkpoint, queue, optimizer overhead

**Corrected text:**
```latex
\textbf{``A fraction of compute'' (V06):} Early stopping reaches the
same final quality (within the V06 non-inferiority margin) at no 
more than one-third the total compute of full-fidelity search. 
Compute is measured in actual accelerator-seconds and wall-clock 
time, recorded by the executor for every trial. Costs include 
startup, training, evaluation, checkpoint save/load, queue wait, and 
optimizer overhead. Full-run equivalents are reported as a normalized 
secondary measure for interpretability, computed by dividing total 
cost by the mean cost of one full-fidelity trial in the baseline arm. 
The one-third threshold applies to measured accelerator-seconds; if 
wall-clock time differs materially due to scheduling or parallelism, 
both metrics are reported and the protocol judges on accelerator-seconds 
(the resource actually consumed). V06 passes only if ASHA delivers 
the factor-of-three savings on actual measured cost.
```

---

## Correction 7: Preregistration and immutable artifacts

**Location:** NEW SECTION after line 199 (after numerical gates paragraph)

**Add:**
```latex
\subsection{Immutable artifacts and preregistration}

Every gate campaign produces an immutable manifest before execution 
begins. The manifest is a signed JSON document containing:

\begin{itemize}[leftmargin=1.3em, itemsep=2pt]
\item Protocol version and entry ID (e.g., V04-T0-v1.2)
\item Task checksums: SHA256 of task code, data files, and environment configuration
\item Seed sets: the exact tuning and test seeds for each method and repetition
\item Analysis script: the decision thresholds, statistical tests, and output format, 
  committed to version control before results exist
\item Environment digest: full dependency lock (pip/conda freeze), hardware 
  description, container or VM image hash if applicable
\item Code under test: the signed git commit or source archive hash
\item Manifest creation timestamp and author signature
\end{itemize}

Results are recorded in versioned JSON with the manifest hash embedded, 
stored in the artifact registry under \texttt{validation/artifacts/} 
(explicitly \emph{not} ignored by \texttt{.gitignore}), and cannot be 
reanalyzed without producing a new manifest version. Changes to 
analysis scripts, decision thresholds, or seed sets after observing 
results produce a new manifest with an incremented version number and 
a documented rationale for the change.

This discipline makes ``p-hacking'' and ``researcher degrees of 
freedom'' \citep{simmons2011false} auditable rather than invisible. 
A reviewer can verify that the analysis plan existed before the data, 
that the code under test matches the git history, and that tasks and 
seeds were not selected post-hoc to favor a particular outcome.
```

---

## Correction 8: V08 release semantics

**Location:** Lines 218-249 (V08 expensive campaigns section)

**Current issue:** Protocol says V08 is a falsifier (can demote but not promote), but Tier 2 completion presumably requires "green"

**Add after line 249 (end of V08 asymmetric stopping paragraph):**
```latex

V08's result states and release semantics are explicit. The entry 
begins in status ``hold: insufficient evidence.'' Three outcomes are 
possible:

\begin{itemize}[leftmargin=1.3em, itemsep=2pt]
\item \textbf{Demote:} All three repetitions on a side agree that the 
population line loses in its home regime. The flagship is demoted to 
an experimental option and the roadmap defaults revert to the Tier 1 
winner (DEHB or BO+ASHA depending on V07).
\item \textbf{Hold:} Repetitions disagree, or the home-regime side is 
inconclusive. The entry remains at ``hold: unresolved at this 
budget.'' The flagship keeps its Tier 2 status as an experimental 
capability but is not promoted to a default recommendation.
\item \textbf{Pass:} To move from ``hold'' to ``pass'' requires a 
full sequential campaign (maximum 10 repetitions per arm per side) 
with preregistered non-inferiority margins and decision boundaries. 
The three-repetition pilot is a tripwire for early cancellation, not 
sufficient evidence for promotion.
\end{itemize}

Tier 2 completion requires V08 not in ``demote'' or ``block'' 
(implementation failure) state. A ``hold'' result is acceptable for 
an experimental late-tier capability: the population line ships as an 
option for users at scale, with the protocol's boundary guidance 
documented but not enforced as a product default. The full campaign 
to reach ``pass'' is deferred to Tier 3 or a post-release validation 
cycle, pending user demand and budget availability.
```

---

## Files to be modified

1. **hpo-survey/sections/16-validation.tex**
   - Apply all corrections above
   - Add new subsections (sampling hierarchy, development/acceptance tasks, multiplicity, artifacts)
   - Update V06, V11 definitions
   - Add V08 release semantics
   - Add citations: holm1979simple, simmons2011false

2. **hpo-survey/refs.bib**
   - Add missing citations if not already present

---

## Review checklist

Before committing:

- [ ] Statistical reviewer assigned and available
- [ ] Statistical reviewer has reviewed all corrections
- [ ] Survey author has reviewed for consistency with rest of document
- [ ] LaTeX compiles without errors
- [ ] All cross-references resolve
- [ ] New citations added to refs.bib
- [ ] Changes tracked in literature-audit.md
- [ ] Git commit with "Statistical corrections to validation chapter per Codex review"

---

## Next steps

1. **Assign statistical reviewer** (Task 1.2, blocking)
2. **Statistical reviewer review** (2-3 days)
3. **Iterate corrections** (1-2 days)
4. **Apply to LaTeX** (1 day)
5. **Rebuild PDF and verify** (1 day)
6. **Update BUILD_PROGRAM_v2 with corrected protocols** (1 day)

**Estimated timeline:** 7-10 days from statistical reviewer assignment
