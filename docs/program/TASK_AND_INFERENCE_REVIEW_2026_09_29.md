# STAT-03/D–E: task sources and mean-inference repair

This is work inside the existing master program. It supplies a pinned candidate catalog, an executable external-table reader, a source/data-quality audit, and a mathematically valid bounded-mean inference candidate. It does **not** freeze acceptance tasks, replace the raw PPO objective, certify a phase, or establish empirical power. The current live design remains incomplete and campaign readiness continues to refuse execution.

## Source-backed catalog

The [catalog](../../validation/designs/tier0_task_catalog_v1.json) is generated offline from the [28-source manifest](evidence/2026-09-29/stat-03/task-sources/manifest.json). Every acquired file has its exact URL, repository/dataset revision, byte count and SHA-256. Git and HuggingFace content uses immutable revisions. OpenML metadata is a dated, hash-bound retrieval; upstream immutability is not claimed. External source files are inspected as data, not executed.

| Source | Concrete acquisition | What it can support |
|---|---|---|
| YAHPO Gym / YAHPO data | Pinned LCBench configuration domain, encoding, objective schema and OpenML task metadata: **34 tasks and 34 dataset IDs** | A candidate inexpensive numeric HPO/architecture-coordinate regime. Domain choices govern eligibility: encoding-only task 167083 is excluded. Dataset IDs are a first lineage grouping, not proof of independent data origins. No surrogate outcomes or model have been evaluated/acquired. |
| ARLBench | All **21 PPO landscape filenames** enumerated; four Brax landscape CSVs acquired, **102,400 rows** in total | External reference/development data and exact table replay. A recorded RL seed/configuration is not an independent HPO study. |
| HPOBench | Pinned tabular/FCNet adapters, data-manager download references and documentation | Concrete candidate source and adapter review. No HPOBench table was adopted: the public LR archive exceeded the 50 MB acquisition cap. The pinned ML tabular adapter also adds a score to model cost (`cost_key = evaluation + '_scores'`); that expression cannot establish elapsed seconds without a separately reviewed correction. |
| Project Brax PPO | Existing Ant/HalfCheetah/Hopper candidate, environment/assets and execution recipe | Required live-workload layer remains. External tables and predicted runtimes cannot certify its mean improvement or measured resource cost. |

Source selection enumerates published domains without filtering for favorable GP/TPE results. The ARLBench optimization-run files were not acquired. The inspected landscapes are explicitly exposed reference/development material, not held-out confirmation. The independent selector/blinding requirement and complete exposure review in survey section 16 remain unresolved. Ant is the workload default; inverted_pendulum has existing development/smoke receipts. No task is declared unexposed merely because a local matching receipt was not found.

`validation/benchmark_catalog.py` verifies source hashes, rejects duplicate or inconsistent cells/configurations, retains blank/nonfinite/absent values separately, and refuses off-table interpolation. `LandscapeTable.lookup` returns a hash-bound recorded observation with **no runtime**. This closes the data-reading/provenance part of the adapter; it does not implement a continuous GP/TPE search over an irregular table or close V01's full equivalence obligation.

## External data cannot supply the missing PPO assumptions

At the final published 50-million-step fidelity, each acquired Brax landscape contains 256 configurations × 10 seeds:

| Environment | Missing/nonfinite of 2,560 | Minimum recorded finite return | Maximum recorded finite return |
|---|---:|---:|---:|
| Ant | 2 | −8.626756 × 10^16 | 6,757.8643 |
| HalfCheetah | 771 (30.12%) | −2.4234055 × 10^21 | 12,480.486 |
| Hopper | 0 | −8.969489 × 10^11 | 3,696.3296 |
| Humanoid | 0 | −5.7034245 × 10^19 | 10,706.277 |

These are faithfully reported external records, not estimates of our current implementation's failure rate or return distribution. The pinned documentation describes 128 configurations, whereas the acquired data contain 256; the audit uses actual unique keys. Published fidelities are 5M–50M; our candidate requests 100K and schedules 101,120–655,360 interactions. The published HalfCheetah example uses `mjx` and 2,048 environments, whereas our candidate uses `generalized` and 32. PPO code, dependencies, domains and evaluation recipes also differ.

Consequently, no numerical scale/reference or positive planning alternative was copied into the live design. Observed minima/maxima can be fixed normalization **anchors** for an explicitly justified target; they are not almost-sure **support bounds** on future returns. Ignoring failed rows or substituting quantiles does not cure that distinction. The installed velocity-based Brax reward formulas do not establish the finite return support needed below. Normalization by a constant also cannot make an unbounded variable bounded.

## Exact mathematical findings

An unrestricted mean cannot be tested with useful uniform finite-sample power. Let a paired gain be +1 with probability .99 and −99 with probability .01. Its mean is zero, yet 20 independent observations are all +1 with probability **.81790694**. Any test that rejects that all-positive sample with probability .8 has null error at least **.65432555**. Making the negative event rarer and larger makes this lower bound approach .8. More bootstrap draws, a normality test, or longer PPO runs cannot prove the missing tail assumption.

The existing loss cap does not justify complete-case inference either. Let a gain be +1 with probability .91 and −.91/.09 otherwise, and let exactly the negative outcomes fail to produce a usable result. Again the full mean is zero. With 20 planned blocks and at most two exclusions, a campaign survives with all retained values positive with probability **.73342959**. This is a selection-bias counterexample, not a forecast. A valid design needs an explicit failure/reliability estimand, a justified missingness assumption, or valid worst-case bounds; counting lost blocks alone is insufficient.

`validation/tier0_mean_feasibility.py` computes both examples exactly and distinguishes necessary power constraints from conservative sufficient ones. For independent differences supported on [−1,1], any level-.025 test with .8 power against the point alternative X=δ must satisfy

\[
\delta \ge (0.8/0.025)^{1/n}-1.
\]

That lower bound is **.189207** at n=20 and **.059463** at n=60. It is necessary for this alternative, not a universal minimum detectable effect. Hoeffding/union-bound sufficient effects are reported separately; their conservatism is not misreported as impossibility or actual power. No scientific effect size is inferred from these artificial examples.

## A valid bounded-mean candidate

`validation/tier0_bounded_mean.py` supplies a fixed-count test of the **mean**, retaining the existing zero superiority null. For independent X_i in [−1,1], set

\[
E_\lambda=\prod_{i=1}^{n}(1+\lambda X_i),\quad 0\le\lambda\le1.
\]

Under the null that the average expectation is nonpositive, independence and AM–GM give

\[
\mathbb E[E_\lambda]
=\prod_i(1+\lambda\mu_i)
\le(1+\lambda\bar\mu)^n\le1.
\]

Thus a fixed mixture E = integral_0^1 E_lambda d_lambda also has expectation at most one, and p = min(1, 1/E) is valid by Markov's inequality. The implementation uses positive-weight Gauss–Legendre quadrature: the integrand is a degree-n polynomial, so ceil((n+1)/2) nodes integrate it without Monte Carlo. The positive normalized numerical weights also define a valid fixed discrete mixture. Log arithmetic avoids product overflow/underflow.

This proof permits heterogeneous task means; it does not require Gaussianity or identical distributions. It **does** require genuinely bounded outcomes and independent rows with a fixed weighting/count. For a nonzero null m, factors `1 + lambda*(X_i-m)/(1+m)` provide a monotone test; inversion supplies a one-sided confidence bound. Component bounds at a selected Holm decision threshold are labeled as decision bounds, not simultaneous confidence coverage for all nine means.

V04 still takes the maximum of its **eight** component p-values (IUT). Holm still controls the two-entry V04/V05 family at .05, and an isolated entry retains .025. Component dependence does not invalidate IUT/Holm. Exact enumeration checks cover skewed two-point nulls, heterogeneous means, confidence coverage and partial-null family boundaries. A correlated-copy counterexample explicitly demonstrates why repeated task/seed labels cannot be treated as independent evidence.

The routine is fixed-count inference. Its batch AM–GM argument does **not** authorize optional stopping under a global average-mean null. Replication remains unused unless a valid repeated-testing rule is prospectively specified. The candidate preview always returns INCONCLUSIVE and `certifies_acceptance=false`; setting its method label cannot bypass the existing campaign guard.

## Sampling and the remaining repair

The v1.1 candidate shared optimizer/training seed schedules across tasks. Candidate **v1.2 repairs that accidental reuse**: each task has a frozen index; its actual stream slot is `block_seed + 20*stream_task_index`. The allocation checks every task/phase/block for collisions and uint32 overflow. Both optimizer construction and PPO evaluation use that slot; study records store it, and endpoint/trace replay rejects mismatches. V05's 675 physical initial configurations were regenerated with these slots, without objective evaluations, preserving identical initialization between its two paired arms. The old candidate/source is archived; the [repair receipt](evidence/2026-09-29/stat-03/task-stream-repair.json) binds 135 distinct slots and 13,500 non-overlapping reserved training/evaluation seeds.

Disjoint pseudorandom namespaces support an independent-stream model but do not prove independence of all execution noise or task populations. Until that model and controlled execution are justified, the conservative unit is a **complete seed vector across the fixed task suite**, giving at most 20 confirmation units. If residual cross-task dependence remains, flattening three tasks × 20 seeds into 60 independent observations is unjustified. Distinct task IDs and a plausible covariance estimate cannot establish independence.

A prospective finite-suite design could assign independent task/study streams and use equal numbers of blocks per task; then the overall study mean equals the equal-task mean. That supports a result conditional on the named suite. Generalization to an RL/HPO task population additionally needs a declared sampling frame, selection probabilities/lineage and uncertainty for task sampling. This review does not silently narrow the registered claim to a convenient fixed suite.

The ordered continuation remains **STAT-03/D–F → final VAL-01 → phase certification → PILOT-01 → CAP-01 → frozen acceptance → REL-01**. D now has pinned source candidates and a negative finding on direct transfer of PPO scales. E has a proved bounded-mean candidate, but its live-task assumptions are unsatisfied. The remaining concrete repair is to prepare the objective/failure-handling and sampling amendment together: either justify support/tail assumptions for the existing raw-return estimand, or explicitly propose a bounded utility target with independently calibrated anchors and report the raw-return mean descriptively. Clipping/relabeling the current result without that amendment is forbidden. Then finish the V01 mapping/equivalence, V02 population, sizing and minimum measured resource proposal.

This is agent-owned scientific preparation. No new user-selected success margin, pilot-order preference or speculative GPU budget is requested. D-PROTOCOL certification remains review of a completed concrete phase proposal, not an invitation to invent statistical inputs. The master and release remain incomplete; no PPO or GPU campaign was run.

Reproduction: `python docs/program/evidence/2026-09-29/stat-03/run_task_catalog_review.py`. The [review receipt](evidence/2026-09-29/stat-03/task-catalog-review.json) binds the catalog, source manifest, script and implementations. The new tests verify actual external failure counts and exact mathematical counterexamples; their success is engineering/mathematical evidence, not project performance evidence.

Verification: **208 affected tests passed** (161 design/inference/evidence tests and 47 governance tests); Ruff, protocol consistency, program consistency, generated-view verification and whitespace checks passed. The [verification receipt](evidence/2026-09-29/stat-03/task-design-verification.json) binds the two JUnit reports and the changed implementation/evidence. Stream repair reproduction is `python docs/program/evidence/2026-09-29/stat-03/freeze_task_streams.py`; it reads the archived candidate, writes v1.2 and performs no objective evaluations.
