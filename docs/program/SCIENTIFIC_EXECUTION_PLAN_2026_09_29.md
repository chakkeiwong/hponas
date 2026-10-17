> Revision 1.20: [scope adoption and current review](SCOPE_ADOPTION_REVIEW_2026_10_01.md) supersedes pending-scope, pre-pilot-effect and unmeasured-installation status below. Follow the structured continuation queue and current master; historical outcomes are retained.

> Revision 1.19: the [phase sequence repair](PHASE_SEQUENCE_REPAIR_2026_09_30.md) supersedes earlier all-external-blocker and pre-pilot-effect requirements. STAT-03 execution is active; historical checkpoints below remain preserved.

# STAT-03 scientific method and resource plan

This revision responds to the user's direction to derive the success criterion, pilot sequence and resource requirement scientifically. It is part of the existing master program. The implementation agent owns this preparation; missing design work is not a request for the user to invent parameters. The previous decision package and version 1.8 authority are preserved in `archive/program-2026-09-29/stat-03-before-scientific-sequence/`.

The zero superiority margin and external-pilot sequence below are adopted for preparation. The completed task/analysis design, actual phase manifests, compute allocation and release are not certified by this document. D-PROTOCOL retains the explicit phase-certification requirement in protocol policy D5.

## Derive the criterion from the claim

For final quality, define the paired task-normalized improvement as candidate minus comparator, oriented so positive is better. For regret AUC, define improvement as comparator AUC minus candidate AUC. Aggregate using the frozen task weights and account for complete study blocks, not individual adaptive trials.

The accepted claim is **superiority**. Its null is H0: Delta <= 0 against H1: Delta > 0. Therefore the margin is zero for both final quality and decision-bearing AUC. This follows from the claim; it is not a user preference, an observed pilot effect or a chosen percentage. The old 5% random/pathological and 15% synthetic diagnostic bars belong to different experiments and remain unchanged.

The numerical decision requires a valid one-sided test and uncertainty estimate. A positive point estimate is insufficient. V04-T0 must clear all eight method/comparator/endpoint components; its entry p-value is their maximum. V05 tests the paired GP encoding comparison. Apply the registered Holm family correction over the two entries at alpha .05. This intersection-union construction controls the composite claim only if the underlying component tests are valid. It does not make arbitrary bootstrap tail counts valid p-values or make all component intervals simultaneous confidence intervals.

Statistical superiority and material benefit are distinct statements. Report effect sizes and uncertainty in objective and normalized units, with the measured resource cost. A nonzero practical margin would need external scientific or decision-utility justification and a different explicit claim. Do not manufacture a universal 5% bar. All pre-existing non-inferiority, equivalence and safety margins elsewhere in the program remain attached to their own claims.

Power cannot be .80 uniformly over every positive effect arbitrarily close to zero. The planning alternative must exceed zero and be justified independently of this experiment's observed advantage: for example by comparable external evidence or a documented benefit/precision requirement. STAT-03 owns researching and freezing that justification before the pilot. If none can be justified, present power and detectable-effect curves and the resulting design limitation; do not select an effect just large enough to make the 20-repeat cap appear powered. A precision-based replacement would require an explicit protocol amendment and could not silently discharge the existing power obligation.

Task selection, normalization scales, regret references, initial objective and task weighting must be fixed without confirmation outcomes. Reference values need provenance. Extra seeds, task renamings and dataset splits are not extra independent task clusters. Finite-suite and task-population claims must be distinguished; the existing program's broader obligations are not waived by a narrow PPO experiment.

## Calibration finding and required repair

The current mechanics tests establish that the candidate implements its stated bootstrap. They do not establish error control. A new engineering diagnostic exercised the actual `joint_bootstrap` under an artificial Gaussian no-effect model with between-task SD 1, within-task SD .5, 20 paired blocks per task, 2,000 simulated datasets and 2,000 bootstrap draws:

| Independent task clusters | Nominal one-sided alpha | Observed false-positive rate | Monte Carlo standard error |
|---|---|---|---|
| 3 | .025 | .127 | .00745 |
| 10 | .025 | .051 | .00492 |

See `evidence/2026-09-29/stat-03/null-calibration-diagnostic.json`. This is an engineering counterexample, not a measured pilot, a universal error-rate estimate or a replacement method. It uses reduced bootstrap draws and cannot certify the registered full analysis. The discrepancy nevertheless rules out treating the current small-task percentile procedure as already validated. Ten tasks is not a magic repair either.

Before campaign spending, STAT-03 must specify and validate an inferential procedure appropriate to the actual sampling design. Check null rejection at the relevant composite boundaries as well as interval coverage and joint power under heterogeneous tasks, skew/heavy tails, correlated components and plausible missingness. Marginal upper-80% variance bounds and estimated correlations are not a simultaneous conservative covariance guarantee. More bootstrap draws address simulation error, not a shortage of independent tasks. If a model-based or randomization-based replacement is used, state and check its assumptions; a sign-flip test is not automatically exact for a mean-null without symmetry or a suitable assignment design.

Preserve the accepted claims and error targets during repair. Expand genuine independent task information or improve the justified inference, rather than moving the success bar after seeing results. STAT-02 remains completed for its candidate engineering deliverable; STAT-03 and final VAL-01 acceptance remain incomplete.

## Scientific execution sequence

1. **Preparation and bounded engineering profiling.** Establish the correct hardware/backend, scientific task scope, external scale references, actual training fidelity, artifact integrity and runtime envelope. Any real-workload profiling has its own reviewed procedure and cap before execution. Its configurations and outputs remain separate from confirmation, and outcome-dependent changes are recorded as development. Read-only inventory and artificial calibration need no campaign data.
2. **Freeze and review the pilot protocol plus the adaptation rule.** Before pilot data, fix hypotheses, tasks and independence units, pairing, endpoints, scales, margins, family alpha, missingness, meaningful planning alternatives, minimum pilot size, variance treatment, null/coverage checks, the sample-sizing algorithm, maximum sample and terminal outcomes. Bind a pilot-specific manifest, disjoint seeds and bounded resource allocation. Obtain phase-specific certification before spending. A pilot report is not a prerequisite for certifying the pilot itself.
3. **Run the external pilot.** Start from the registered minimum of five complete independent paired blocks per task, with every arm in each block. This is a variance/feasibility pilot, not a powered success test. Use it for nuisance variability, correlations, completion rates and actual throughput. Do not use its observed advantage to choose the hypothesis, margin, favorable task subset or planning alternative. No pilot observations enter confirmation. Five is a minimum, not assurance of a precise variance estimate; any inadequacy triggers the predefined diagnosis/replanning rule rather than unrecorded replacement seeds.
4. **Apply the frozen sizing rule.** Validate error/coverage behavior and simulate the full conjunctive entry at the correct family adjustment. Report simulation uncertainty; a noisy estimated power of .800 is not proof that true power is at least .80. Choose replicate counts for the frozen task set and the measured budget permitted by the rule, within the current 20-repeat cap. If task diversity, power or affordability is inadequate, report that result and revise the design prospectively with a new freeze; do not select favorable tasks, lower standards or collect until significance.
5. **Freeze and certify confirmation.** Record selected counts, full data/code/environment identities, cost ceiling, stopping rule and any permitted replication/error-control plan before confirmation. If pilot learning requires a change outside the predeclared adaptation rule, version and re-review the protocol before using fresh confirmation data. Run confirmation once with disjoint seeds and no unplanned peeking, then recompute the registered analysis and release evidence.

An optional rescue replication does not obtain another unadjusted chance at the same alpha. The existing one-replication cap is a spending/stopping rule, not repeated-testing error control. STAT-03 must supply a prespecified valid two-stage rule, or leave that optional path unused. A combined test, alpha spending or another justified rule must be fixed before the first confirmation result. This finding remains part of the analysis freeze.

This is the standard external-pilot sequence for the existing design. A valid internal-pilot or adaptive alternative is possible, but is not what this program has registered. There is no outstanding user preference question about whether pilot comes before confirmation. Scientific certification remains a review of the completed concrete protocol.

## Resources and a costed staging rule

The read-only inventory and arithmetic are reproducible with `evidence/2026-09-29/stat-03/collect_resources.py`; the receipt is `resource-envelope.json` in the same directory. No PPO evaluations were executed for this plan.

The host exposes four NVIDIA GPUs, 256 logical CPUs, approximately 252 GiB RAM and about 1 TiB free storage. Availability is a snapshot, not a reservation. The project Python currently reports only a JAX CPU device and has no JAX CUDA plugin installed. Thus GPU throughput is not established even though GPUs are visible. Prepare a separate, pinned CUDA-capable JAX/Brax environment and verify it before making an accelerator schedule. Do not modify another project's environment or infer a free GPU from a momentary utilization reading.

A sensible initial reservation proposal is **two GPUs, 16 CPU cores, 64 GiB RAM and 100 GiB working storage**, with one sequential worker per study and separate studies on isolated devices. These are engineering starting allowances, to be checked by bounded profiling rather than claimed as measured minima. One GPU is a valid slower option. The current campaign loop is sequential, so VAL-01 must verify isolation, receipt completeness and scheduling for two concurrent studies before the two-device schedule is executable. Each arm receives the same resource policy; changes in occupancy must not bias elapsed-budget comparisons.

Actual fidelity matters. In the installed Brax training schedule, the candidate 100,000-step target results in 101,120 to 655,360 training interactions over the allowed integer batch sizes, before evaluation interactions. Batch sizes 64, 256 and 512 schedule 163,840, 327,680 and 655,360 interactions respectively. These are source-derived counts, not observed speed. Every compiled shape/configuration, PPO evaluation and optimizer cost must be represented in profiling. The retained 128-step smoke examples cannot be multiplied into a trustworthy forecast.

For T tasks shared by the two entries, five pilot blocks cost **30T complete studies**. Confirmation costs **T(4 n04 + 2 n05)**, up to **120T** studies at the registered n04 = n05 = 20 cap. The current three-task candidate therefore entails 90 pilot studies and up to 360 confirmation studies, or 450 total. This is not evidence that three tasks suffice. Fifty adaptive trials is a per-study safety ceiling; it is not the repetition count or the measured resource budget. A permitted maximum-size replication would add up to 360 studies for this candidate.

Sum each study's declared elapsed budget and charged overshoot, then add measured external profiling, audits, protected evaluations where required, and storage/operational costs without double counting optimizer overhead already charged inside the study. For unequal task sets or budgets, sum the actual task/entry allocation rather than using the common-T shortcut.

The following are conditional planning scenarios for the current three-task candidate at the maximum confirmation count. The 20% reserve is illustrative planning headroom, **not** a measured cost, a statistical overshoot tolerance, a resource approval or a completion forecast:

| Assumed reserved time per complete study, including overshoot | Pilot + maximum confirmation, plus 20% reserve | Ideal elapsed days on two reserved GPUs |
|---|---|---|
| 30 minutes | 270 GPU-reservation hours | 5.6 |
| 1 hour | 540 GPU-reservation hours | 11.3 |
| 2 hours | 1,080 GPU-reservation hours | 22.5 |

These figures exclude preparation, tabular acceptance, CPU sizing/mutation work and optional replication. With one GPU the device-work duration doubles; additional independent tasks and changed study budgets change the total. Sequential pilot/analysis/confirmation barriers and actual utilization add calendar time. They are reservation hours, not measured active GPU seconds.

Stage the request: complete the statistical and backend repairs, prepare a short representative profiling protocol with a proposed maximum of two GPU-reservation hours, then quote the bounded pilot from measured full-fidelity study costs. This two-hour profiling cap is a proposal, not authority to spend or a guarantee that profiling will finish. Release confirmation capacity only after the frozen pilot-based sizing rule succeeds. The agent prepares the measurements and resource request; the user need not invent study seconds, task counts or a budget from no evidence.

CPU work includes V01/V02 conformance and stochastic-equivalence design, joint sizing/calibration and V03-03's existing cap of four workers for six wall-clock hours. The complete master also includes later tiers, whose scientific workloads are not yet frozen. This is a Tier 0 envelope; it cannot honestly serve as a total-program price or release date.

## Program disposition

Master revision 1.9 makes STAT-03 active, assigns scientific derivation to the implementation agent, and adopts the pilot-then-confirmation procedure for preparation. D-T0-DESIGN records that ownership and method direction, not acceptance of an unfinished task manifest. D-PILOT-ORDER records the phase sequence, not a pilot spend authorization. The candidate AUC margin is zero and pilot counts are five; other unsupported numerical inputs remain unfilled.

STAT-03 now owes the validated task/inference design, external scales/planning alternatives, V01 equivalence design, V02 coverage, and measured-resource proposal. VAL-01 then completes affected adapters and guards, including any inference and isolated execution repairs, before the frozen pilot is certified and run. PILOT-01, CAP-01, final V03-03/PPO-01 and REL-01 retain their gates. No historical campaign is relabeled and no phase is declared complete.

The basis is the accepted claims and error policy in `validation/protocols.json`, the methodological corrections in `RESPONSE_TO_CODEX_STATISTICAL_REVIEW.md` sections 1–5, and the fresh implementation/inventory evidence above. The protocol register remains DRAFT. Its D5 instruction, “PI certifies the final protocol set before any campaign spend,” applies to each complete phase protocol before that phase spends resources; it does not require the user to design the study or prevent authorized preparation.
