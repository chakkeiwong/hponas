# Fixed local program operations

12 October 2026. These commands implement the user's request to reduce repeated approvals for the authorized HPO-NAS repair program. Run the absolute executable and the single operation **exactly as written**. Do not prefix environment assignments, use a Python/shell wrapper, append flags, or chain commands. The helper sets the working directory, interpreter, numerical thread limits, test roster and unique output directory.

| Exact command | Work and writes | Bound |
|---|---|---|
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py status` | Reads the current master/register and source; prints the active step and blockers | Small local read |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py checks` | Regenerates program views and runs the six existing checks; retains logs/receipt | Six serial processes, at most 300 seconds each |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py test-study` | Fixed Study/evaluation/checkpoint/vector regressions, then two owned local Ray groups: existing streaming/declared workflows and repeated scalar/vector barriers | Three serial processes, 300 seconds each |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py test-search` | Static whole-test collection, actual-candidate mutation proof contexts, then three fixed searcher/GP/capability groups preserving the complete ordered roster | Five serial processes, 300 seconds each |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py test-store` | Fixed SQLite store/backup/atomic recovery, then private PostgreSQL/worker/declared recovery verification | Two serial processes, 300 seconds each |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py test-schedulers` | Fixed scheduler/report/rung/state regression roster | One process, 300 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py test-operations` | CLI refusal, collection-check controls, installer overwrite/symlink refusal, owned-process timeout tests | One process, 300 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py check-rules` | Evaluates positive/negative command matches using installed Codex; compares installed bytes | One process, 300 seconds |

The runner uses one available CPU, one numerical thread and hides GPUs. Runs are serialized and logs/receipts are retained under `docs/program/operations-runs/`. A failed process stops its group; timeouts terminate the owned process group and retain failure. Scientific source is fingerprinted before/after. These are development checks, not campaign PASS evidence. `status` does not claim that an arbitrary background run is healthy.

The runner never accepts a script path, arbitrary shell, arbitrary pytest arguments, destination or environment from its CLI. New relevant tests must be added to the reviewed fixed roster before use. Operational tooling is outside the scientific source inventory and is separately hash-bound in program evidence; this does not exempt it from review. Existing registered scientific dependencies, tests and protocols retain their original source rules.

The reviewed local-services helper adds live coverage under
`PRD-01/LOCAL-OPERATIONS-CLOSURE`. Its fixed PostgreSQL mode initializes a private
temporary cluster using existing binaries, listens only on its private Unix
socket, and runs the four named backend/worker/declared suites. Its fixed Ray
mode runs the existing streaming suite and declared artifact/recovery case;
the separate fixed `ray-repeated` mode runs the repeated scalar/vector barrier
case. All seven live Ray cases are retained in serial groups. Each helper keeps
its existing 235-second test deadline and 275-second total deadline; verbose
case progress, durations and a 60-second stack dump diagnose timeout failures.
Both backends retain XML, logs and a
cleanup receipt in the runner's unique output directory; zero skipped tests
are required. Tests use one CPU affinity and no GPU; the cooperative worker
contention fixture uses at most four processes on that CPU. The helper tracks
only its own descendants and stops them on completion or timeout. It performs
no download, external deployment or separate-machine test. These roster changes
do not change the installed command rules or prove managed approval bypass.

## One grouped rules installation

The reviewed candidate is [hponas-program.rules](../program_operations/hponas-program.rules). The fixed installer is:

```text
/home/ubuntu/workspace/hponas/program_operations/install_approval_rules.py
```

It pins the candidate, checker and runner hashes; exercises 40 matching/refusal cases with the installed Codex CLI; creates only `/home/ubuntu/.codex/rules/hponas-program.rules`; refuses a different existing file or symlink; and records a readback receipt. It accepts no arguments. The directory is outside this session's writable roots, so the managed tool layer requires one installation approval. That request covers the reviewed group of fixed commands, not arbitrary execution.

The dedicated file contains direct command prefixes and exact `/bin/bash -c`/`-lc` envelopes for hosts that present those forms. It contains no generic Python, shell, network, git, deployment or scientific-campaign rule. Prefix rules can match extra trailing argv; the executables reject such arguments before doing work. Shell strings with extra commands do not match the dedicated envelopes. Other previously installed global rules remain separate: these tests verify this dedicated file and do not claim to revoke or narrow unrelated permissions.

The installer does not edit `default.rules` or sandbox settings. The managed approval service may separately persist the approved installer prefix; it did so in this session. Repeated dated HPO-NAS commands in the accumulated default file are superseded operationally by these stable entry points, not deleted from global policy. New work outside this manifest must first be made concrete, then bundled into one scoped request when the managed layer actually requires it. Existing authorization covers ordinary workspace edits and bounded local repairs; do not ask again at every phase.

Rule syntax/matching is verified with the installed `codex execpolicy check`. The official documentation endpoint returned HTTP 403 inside and outside the sandbox during this review. Installed-rule byte equality and matcher results do not prove the running host has reloaded the file or eliminate other managed approval controls. Report actual activation evidence accurately; never use alternative execution routes to evade a rejected approval.

## Continue without drift

Read the active stage and its dependencies. At each boundary, retain the result, repair observed defects, update the next stage's concrete tests/resource allocation, synchronize the master/register and continue eligible work. A proposed “next” action must name its master stage and whether it changes scope. Continue master execution until a real blocker, explicit user pause, or whole-master completion; distinguish answering a status/scope question from claiming the master is complete. Do not label queued work “running,” or a development check “scientific acceptance.”

## Completed-failure survivor diagnostic (23 October 2026)

Exact one-time operation:
`/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-23/gap-survivor-repair-01/run_diagnostic.py`

The adjacent `diagnostic-plan.md` and `diagnostic-review-01.json` define 151
retained targets, three clean baselines, one CPU, no GPU, 15 seconds per fresh
child and a 2,550-second independent guard with 4-GiB owned-RSS cap. This is a
contract diagnostic in BANK-01/GAP-QUALIFICATION, not an official campaign.
It refuses stale inputs, extra arguments, existing outputs or an active run.
The fixed focused tests and exact retained functions are bound before launch.
No service, network, deployment or global permission change is requested.


## GAP-01 exact operations (18 October 2026)

The additive reviewed manifest is `docs/program/GAP_CLOSURE_PROGRAM_2026_10_18.md`.
The runner rejects extra arguments; it uses the existing one-CPU, no-GPU,
300-second, serialized receipt engine. Test rosters are reviewed as each feature
is added. These commands do not allocate scientific campaigns.

| Exact command | Purpose |
|---|---|
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py check-plan` | Atomic inventory, owner and final-stage dependency checks |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py check-rules` | Exact positive/negative GAP rule matches |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py test-boundaries` | CLI refusals, false-completion counterexamples, and GAP test dependencies executed in the actual isolated V03 input snapshot; no mutation campaign |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py test-mo` | Multi-objective joint batch and Study regressions |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py test-evaluation` | Evaluation, repetition and method routing regressions |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py test-population` | Population adapter and recovery regressions |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py test-local-ops` | Temporary local operations and access/meter regressions |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py test-transfer` | Ranked/RGPE and source-history regressions |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py test-adapters` | Fixed bank/caller/V03 regressions, then offline wheel build/install and shipped caller/resume/base API verification on Python 3.12/3.13 |
| `/home/ubuntu/workspace/hponas/program_operations/gap_ops.py audit-closure` | Final clause/source audit; refuses unfinished work |

`test-adapters` runs two serial processes. Its installation helper accepts no
arguments, uses the unique operation directory and retained offline resources,
and creates fresh environments without changing the retained runtimes. The
helper has a 270-second total deadline and a 60-second limit per subprocess,
within the operation's 300-second process bound. All descendants inherit the
operation process group; timeout cleanup records remaining owned processes.
Installed CLI runs execute outside the checkout with PYTHONPATH removed.
Wheel/source/install bytes, dependency manifests, origins, both caller models
and completed resume are retained. This is development installation evidence,
not scientific qualification or a new campaign allocation.

The `test-population` roster also includes the inherited independent population
evidence and finite-campaign regression suites. PAR-QUAL-01/PREPARE added these
after calibration exposed callable finite-MDP compatibility loss. The existing
one-CPU/no-GPU/300-second development bound remains unchanged.

One grouped protected installation:

```text
/home/ubuntu/workspace/hponas/program_operations/install_gap_rules.py
```

It creates only `/home/ubuntu/.codex/rules/hponas-gap-closure.rules`, refuses a
symlink or different existing file and records pinned inputs/matcher/readback.
The official rules page returned HTTP 403 both inside and outside the sandbox;
installed matcher verification is the available syntax evidence. Dedicated rules
do not override managed approvals or prove the host has reloaded the file.

## GAP qualification preparation and execution

The reviewed prospective manifest is
`docs/program/evidence/2026-10-18/gap-admission-01/admission-plan.md`.
Two additional exact, no-argument operations are prepared:

| Exact command | Purpose and limit |
|---|---|
| `/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-01/review_program.py` | Serial deterministic controller/transition controls and input/installation reconstruction; 300 seconds, one CPU, no GPU; no campaign or service launch |
| `/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-01/run_gap_program.py` | One reviewed durable user service: bounded admission, then one prospective 17-entry/25-job qualification allocation after prerequisites pass; 45,000-second outer limit, no automatic restart or retry |

The launcher binds its drivers and exact inputs before launch, uses only the
fixed `hponas-gap-qualification-20261018-01` service and refuses extra arguments
or consumed outputs. Its managed host-service approval is requested once for
this concrete bounded sequence. Existing GAP rules continue to cover routine
operations. No global interpreter, shell, network or deployment rule is added.
The scientific package advances to GAP-01/FINAL-AUDIT and cannot mark the
master complete. The final independent audit remains the last phase.


## Repaired-source successor and final audit (19 October 2026)

The consumed admission/qualification01 and reviewed-but-unlaunched audit09
remain historical. The active prospective group is admission02,
qualification02 and audit10, within the existing BANK-01/GAP-QUALIFICATION
then GAP-01/FINAL-AUDIT master stages. There is no scope expansion.

| Exact command | Purpose and limit |
|---|---|
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-02/review_launch.py | Compile and reconstruct pinned controls, retained integration and audit preflight; 300 seconds, one CPU, no GPU or scientific campaign |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-02/run_gap_program.py | One no-argument service hponas-gap-program-20261019-02: fresh admission, one 17-entry qualification, terminal reconstruction, final seven-group audit; 66000-second ceiling |

The concrete manifests are gap-qualification-02/plan.md and
gap-final-audit-10/audit-plan.md under docs/program/evidence/2026-10-18.
Restart=no, KillMode=control-group and TimeoutStopSec=30 apply. ExecStopPost
records noncompletion and releases a stopped freeze without retry. Each
scientific run has its original guards and no output is reused. V03's reviewed
internal ceiling is 36000 seconds, its outer bound 36900 seconds, at most
24 CPU slots, eight high-memory children, 52 GiB child reservations and an
independent 64-GiB RSS guard; no GPU. Disk admission is 32 GiB, stop below
16 GiB. Resource scenarios are not statistical confidence bounds.

The grouped managed request covers only this exact fixed launcher, its
owned local sockets and service, all admission/qualification/audit children,
and the fixed stop handler. Request the executable-specific approval prefix;
this is an additive allow-list change and needs no broad interpreter/shell
or protected global-rule edit. Managed rejection remains authoritative.
No campaign is allocated merely by review or by matching a rule. The final
audit cannot run before current qualification passes, and neither a service
exit nor mutation PASS alone can mark the master complete.


## Calibration-resource successor (19 October 2026)

Admission02 is consumed FAIL: complete statistics and both fixed mutation
controls finished, but the mandatory Ray order check exhausted the shared
1,500-second deadline. Its evidence is immutable. Prepared resume02 is
ineligible because it requires passing admission. Qualification02 was never
allocated. Audit11 preflight/review remain development evidence on that source.

The current prospective sequence is admission03, qualification03 and audit12,
within BANK-01/GAP-QUALIFICATION then GAP-01/FINAL-AUDIT. V03 2.29 changes only
the prospective complete calibration ceiling to 2,700 seconds (2,850-second
guard; 2,880-second controller bound). The measured engineering rationale is
calibration-repair-plan-01.md and calibration-failure-analysis-01.json under
gap-qualification-repair-01. All scientific criteria, controls, tests and the
36,000-second campaign ceiling remain unchanged. Failed admission is not reused.

| Exact command | Work and bound |
|---|---|
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-03/review_program.py | Fixed controller/import/development/audit controls; at most 4,100 seconds; no scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-03/review_launch.py | Final exact bindings and resource arithmetic; 300-second review; no scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-03/run_gap_program.py | One hponas-gap-program-20261019-04 service: complete fresh admission, 17 scientific entries and five gates, terminal reconstruction and final 27-clause audit; 68,000-second ceiling |

The 13 fixed steps total at most 66,930 process-seconds within the service
ceiling. Restart=no, KillMode=control-group, TimeoutStopSec=30, exclusive outputs
and a fixed stop handler apply. The full scientific allocation remains 45,720
process-seconds plus 6,000 seconds of registrations; final audit is capped at
6,000 seconds. These are hard resource limits, not duration guarantees.
CPU/memory/disk/no-GPU controls are unchanged. The explicit runner_witness
import and archived-guidance hash reconciliation are reviewed in this successor.

Request one exact executable-specific managed host-service approval after the
complete package is reviewable. Existing routine rules remain sufficient; no
global interpreter, shell, network or deployment permission is broadened.
Managed rejection remains authoritative. Success requires every frozen result
and the complete last-phase audit; service exit alone cannot close the master.


## Completed-failure survivor-repair successor (23 October 2026)

The historical admission03/qualification03 is consumed: its complete V03
result is FAIL, not an interrupted result eligible for retry. The active
prospective package is admission04, qualification04, descendant04 and final
audit13. It stays within BANK-01/GAP-QUALIFICATION then GAP-01/FINAL-AUDIT.
The concrete repair sequence is
docs/program/evidence/2026-10-23/gap-survivor-repair-01/successor-plan.md.
Earlier launch commands remain historical and must not be reused.

The fixed test-adapters command now builds offline in a fresh build environment
with retained setuptools 84.0.0 and wheel 0.45.1. It verifies all declared
package files against SHA-256 RECORD entries and rejects unbound inputs; the
package-manager lock is separately bound and not imported. The retained
installation runtimes remain unchanged. The operation retains its 270-second
helper deadline, 60-second subprocess limits and complete installed workflows.

| Exact command | Purpose and bound |
|---|---|
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-04/review_program.py | Serial current development/install reconstruction, service/controller refusal controls and six independent audit rehearsals; 4,100 seconds, one CPU, no GPU, no scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-04/review_launch.py | Exact handoff bindings, governance and resource arithmetic; 300-second review, no scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-18/gap-admission-04/run_gap_program.py | One hponas-gap-program-20261023-01 service: fresh calibration/cleanup admission, 17 scientific entries and five gates, then terminal reconstruction and complete 27-clause final audit; 68,000-second ceiling |

All numerical thresholds, population/operators, selection rules, no-GPU and
CPU/memory/disk controls are unchanged. V03 2.30 prospectively adds only the
exact optional-fidelity default proof; diagnostic outcomes cannot be imported.
The thirteen service steps total 66,930 seconds. Restart=no, KillMode=control-group,
TimeoutStopSec=30, exclusive outputs and the fixed stop handler apply. No
campaign is allocated until complete review and fresh admission pass. Group
any managed approval for this exact launcher and owned sockets/service/children;
no global interpreter, shell, network or deployment rule is requested.


## DOC-01 documentation and application operations (24 October 2026)

Reviewed manifest: docs/program/evidence/2026-10-24/doc-01/operation-manifest-01.json.
Commands own their environment, one CPU affinity, disabled GPU, fixed inputs,
timeouts, outputs and logs. Companions are separately verified; core qualification
is not transferred. Examples have 1,200 seconds each (2,400 combined); other
subprocesses have 300 seconds. No network, sibling imports, services or campaign.

| Exact command | Purpose |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py audit | All 123 requirements, 131 semantic rows, 27 clauses and source/evidence |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py test | Companion numerical, derivative, role and tamper tests |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py response | One finite response HPO allocation, full oracle and 12 studies |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py equilibrium | One finite trained equilibrium NAS allocation and 12 studies |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py verify | Independently reconstruct both successful allocations |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py smoke | Shipped hinge/allocation commands and completed resume |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py render-results | Generate tables and standalone figure from retained summaries only |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py runtime | Read back fixed runtime versions/origins and source context hashes |
| /home/ubuntu/workspace/hponas/program_operations/doc_ops.py build | Four-pass pdflatex/BibTeX build with retained logs |

No automatic repeat of passing examples. Retain failed attempts; corrections
need reviewed successor manifests. Managed approval rejection remains binding.

DOC-01 successor manifest operation-manifest-03.json adds fixed result rendering and the executable manual snippet to smoke tests; prior consumed inputs remain bound in their receipts.

DOC-01 successor manifest operation-manifest-04.json adds fixed runtime readback and a false-regret negative control. No accepted application allocation is repeated.

DOC-01 final completion checker (no arguments):
/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-24/doc-01/final_review.py
The adjacent final-review-manifest.json pins all inputs and the checker. It has
a 300-second bound, performs no fitting/network/service action and writes only
final-review.json. The original terminal GAP-01 audit still follows it.

## APP-01 five-family application validation (24 October 2026)

Reviewed authority: docs/program/WORKSPACE_APPLICATION_VALIDATION_MASTER_2026_10_24.md. Inputs are pinned in docs/program/evidence/2026-10-24/app-01/manifest-current.json; consumed manifests and source versions remain immutable. One CPU, no GPU/network; 4-GiB owned RSS, 256-MiB output, 2-GiB starting disk floor. Family limits 1,200 seconds; others 300. No automatic rerun of successful allocations.

/home/ubuntu/workspace/hponas/program_operations/app_ops.py controls
/home/ubuntu/workspace/hponas/program_operations/app_ops.py forecast
/home/ubuntu/workspace/hponas/program_operations/app_ops.py wallet
/home/ubuntu/workspace/hponas/program_operations/app_ops.py policy
/home/ubuntu/workspace/hponas/program_operations/app_ops.py nas
/home/ubuntu/workspace/hponas/program_operations/app_ops.py transport
/home/ubuntu/workspace/hponas/program_operations/app_ops.py verify
/home/ubuntu/workspace/hponas/program_operations/app_ops.py synthesis
/home/ubuntu/workspace/hponas/program_operations/app_ops.py audit

## APP-02 sequential investigation (25 October 2026)

Authority: docs/program/evidence/2026-10-25/app-02/plan-01.json. First operation only re-scores saved NAS weights and summarizes retained policy/sampler evidence; no training, search, or new chain. Bound manifest diagnosis-manifest-01.json, one CPU, no GPU/network, 300 seconds, 2 GiB RSS, 8 MiB outputs. Requires active APP-02/NAS-REPLAY and refuses repeating a successful allocation.

/home/ubuntu/workspace/hponas/program_operations/app_diagnose.py

APP-02/NAS-ISOLATE fixed paired intervention: isolation-manifest-01.json pins 48 fits, widths4/8, three data replicates, four fixed seeds, two training-data roles, and checkpoints120/240/480. At epoch120, reproduce20 original fits before interpreting longer training. Original thresholds, model source and APP-01 evidence remain unchanged. Same300-second/one-CPU/2-GiB/8-MiB diagnostic limits; no HPO or automatic repeat.

/home/ubuntu/workspace/hponas/program_operations/app_nas_isolate.py

APP-02/NAS-ISOLATE post-fit independent reconstruction (no new fitting):
/home/ubuntu/workspace/hponas/program_operations/app_nas_review.py
The fixed nas-review-manifest-01.json binds every paired model; reconstruct144 checkpoints, repeat20 original-weight comparisons and reject omitted cells/false feasibility counts under the same diagnostic resource limits.

## APP-02 wallet mathematical preflight

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_wallet_preflight.py

Runs all 24 likelihood/gradient controls, independent analytic-risk/allocation checks and exactly three representative fits (three starts each). One CPU, no GPU/network, 180-second guard, 2-GiB RSS, 8-MiB output. Manifest: evidence/2026-10-25/app-02/wallet-preflight-manifest-01.json. Refuses changed inputs, inactive stage or consumed successful allocation. No broader HPO or core qualification is implied.

## APP-02 wallet measured search diagnostic

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_wallet_study.py

Runs exactly72 finite-reference fits,384 public-Study tuning fits and12 final refits over three synthetic datasets; three optimizer starts per fit. One CPU, no GPU/network,300-second guard,4-GiB RSS,64-MiB output. The reviewed wallet-study-manifest-01.json binds the passing mathematical/profile evidence, source and operation. Retains categorical configuration identities, all repeated proposals, final-role isolation and exact-distribution diagnostics. No sibling dependency or core qualification change.

## APP-02 wallet independent reconstruction

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_wallet_review.py

Reconstructs all468 wallet fits and12 studies from bound saved artifacts, verifies split identities and stationary fits, compares independently written scalar likelihoods, refines population integration and rejects missing-study, altered-score and leakage controls. Zero new fits;180-second guard,one CPU,no GPU/network,2-GiB RSS,8-MiB output. Source-bound wallet-review-manifest-01.json preserves every consumed input.

## APP-02 wallet fresh selection comparison

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_wallet_selection.py

Reviewed wallet-selection-plan-01.json allocates294 fits:24 candidates across holdout and3-fold CV,3 fresh datasets,6 final refits. Local exact-enumeration adapter; cursor/recovery/exhaustion controls; independent scalar scores and selection reconstruction. One CPU,no GPU/network,180 seconds,2-GiB RSS,32-MiB output. No superiority presumption or qualified core edit.

## APP-02 wallet final analysis

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_wallet_close.py

Reconstructs all294 fresh-selection fits and mean-fold selection; verifies final models and known-law metrics. Derives paired loss-difference variance via truncated moments through order4, checked by independent quadrature. No new fits/simulation;180 seconds,one CPU,no GPU/network,2-GiB RSS,8-MiB output. Post-selection contrasts are descriptive only; wallet-close-manifest-01.json binds inputs.

## APP-02 fresh NAS refit comparison

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_refit.py

refit-design-02.json/refit-manifest-02.json allocate48 fresh paired fits; widths4/8,training sizes48/80,two initializations,three datasets,random vs8 boundary-point replacements.120/480 checkpoints independently re-score with NumPy and torch; original derivative thresholds unchanged. One CPU,no GPU/network,180 seconds,2-GiB RSS,16-MiB output. No final-driven HPO or continuous-domain guarantee.

## APP-02 matched transport diagnosis

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_transport.py

transport-design-01.json and transport-manifest-01.json allocate30 matched map/length/seed pairs,19200 transitions total; step.15,length1/8,identity/exact/three frozen learned maps. Gradient/reversal/volume checks and exact Gaussian-flow correlation reference. No training or posterior-driven selection.180seconds,one CPU,no GPU/network,2GiB RSS,16MiB output.

## APP-02 policy-class repair

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_policy.py

policy-design-01.json/policy-manifest-01.json allocate exact512-policy dual reconstruction plus222 fresh fits across legacy24/repaired48 configurations and3 paired datasets. Local successor adds both threshold directions; public Study and independent DR scoring.120seconds,one CPU,no GPU/network,2GiB RSS,32MiB output; no real-bank policy recommendation.

## APP-02 independent final review

Exact command: /home/ubuntu/workspace/hponas/program_operations/app_final_review.py

final-audit-manifest-01.json binds11 completed operation receipts and their input closure. Reconstruct96 fresh NAS checkpoints,19200 transport transitions,512 exact policy values and222 policy scores; verify prior762-wallet-fit reconstruction evidence. Five altered/missing-evidence controls. Zero new fits;300seconds,one CPU,no GPU/network,2GiB RSS,8MiB output. Requires active final-review stage and refuses consumed success. Scientific limitations remain explicit.

## APP-03 bounded application repairs

Authority: docs/program/APPLICATION_REPAIR_MASTER_2026_10_25.md. Fixed runner accepts one named operation only; each requires its active master stage and separately reviewed source/input/limit manifest in evidence/2026-10-25/app-03. One CPU, no GPU/network,4GiB RSS,64MiB output,2GiB starting disk. Refuses any consumed allocation; failures require reviewed successor operations. No package requalification or broad campaign implied.

/home/ubuntu/workspace/hponas/program_operations/app_repair.py wallet

Wallet:72 candidate fits,3 fresh datasets,public Study decision-utility selection,independent scalar controls,simultaneous bounded-utility intervals and MNAR nonidentification witness;300seconds. Final evaluation reuses the identical frozen training-only policy and charges scoring work; no hidden refit or repeat fitting.

/home/ubuntu/workspace/hponas/program_operations/app_repair.py nas-repair

APP-03/NAS-REPAIR:24 matched fits,original derivative limits,2 widths,2 geometries,3 recipes,2 seeds;300seconds. Training81 rows,480Adam steps and at most80 L-BFGS steps/100 evaluations. Freeze recipe using41x41 validation only before fresh confirmation. Independent NumPy/torch scoring.

APP-03/NAS precision successor (first allocation failed independent reconstruction):
/home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py nas-repair-v2

Consumes nas-repair-v2-manifest.json; restores model tensors in float64. Same24-fit roster and300second bound; one failed first-fit attempt additionally charged. Original runner/source/evidence remain immutable. No threshold relaxation.

/home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py nas-confirm

APP-03/NAS-CONFIRM: six fresh seeds, same frozen recipe selected using development validation;81x81 final mesh and512 random points per fit;180seconds. No final-score reselection or retries.

/home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py transport

APP-03/TRANSPORT:5 maps,2 frozen policies,2 fresh seeds,4chains,8192 gradient evaluations per chain including2048warmup;600second guard. At most200240 transitions/655360 gradient budget. All pairs retained; basic split-Rhat and batch-means diagnostics do not certify convergence.

/home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py policy

APP-03/POLICY:21 nuisance fits,291 policy scores,3 datasets,48 repaired configurations and2 crossfit folds;180seconds. Independent path enumeration/DR scoring,held-out selection assessment,overlap/unknown-identification refusals and observational-equivalence witness.

/home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py forecast

APP-03/FORECAST:27 fits,3 fresh datasets,4 lag/regularization candidates,2 rolling-origin folds and sealed final evaluation;180seconds. Embargo observations masked while state propagates. Independent Gaussian-conditioning/ridge reconstruction and future-feature,gap,entity,final-exposure refusals.

/home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py documentation

APP-03/DOCUMENTATION: versioned main-app03 manual and repair guide;four-pass LaTeX build and extracted-text/source-closure checks.300seconds,no fitting,immutable predecessor preserved.

/home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py audit

APP-03/FINAL-REVIEW: independent reconstruction of75 wallet evaluations,24+6 NAS models,20 sampler cells,291 policy scores and27 forecasts;complete hash/roster controls and19 altered-evidence refusals.300seconds,zero new fits,fixed-RNG replay only;terminal GAP audit follows.

## SCI-01 scientific gap trace (25 October 2026)

/home/ubuntu/workspace/hponas/program_operations/scientific_gap_trace.py analysis

Reviewed scientific-gap-trace-01/analysis-manifest.json: saved wallet paired uncertainty,20 retained sampler diagnostic cells,138 retained ifBO PI tensors and6 NAS interval-bound attempts. Zero new fits,chains or pretrained forwards.300seconds,one CPU,no GPU/network,2GiB RSS,16MiB output. Candidate interval certificates require independent review. No old verdict/threshold or qualified source change.

/home/ubuntu/workspace/hponas/program_operations/scientific_gap_trace.py review

Reviewed scientific-gap-trace-01/review-manifest.json: independently rederives all six saved NAS interval-bound candidates with an explicit 2x2 Hessian chain rule, exact dyadic binary64 weights,50-digit outward intervals, complete partition checks and negative controls. Zero fits,chains or pretrained forwards;300seconds,one CPU,no GPU/network,2GiB RSS,16MiB output. This review closes only the stated six-network mathematical domain claim and does not qualify floating-point inference, unseen seeds or real-bank effectiveness.

## SCI-02 bounded scientific companion repairs (25 October 2026)

Reviewed scope: docs/program/SCIENTIFIC_GAP_REPAIR_2026_10_25.md. Each operation requires its active master stage, single-use manifest, pinned source/runtime and passing prerequisites. One CPU, no GPU/network, zero new fits, pretrained forwards or sampler chains; 2 GiB RSS and 32 MiB output. No arbitrary arguments. Companion evidence does not alter core qualification or prior scientific verdicts.

/home/ubuntu/workspace/hponas/program_operations/scientific_gap_repair.py ifbo

SCI-02/IFBO: all 138 retained PI tensors, six traces, unchanged tolerance and independent upstream-body/negative controls; 300 seconds.

/home/ubuntu/workspace/hponas/program_operations/scientific_gap_repair.py nas

SCI-02/NAS: optional checker for the explicit SiLU/exp(-x*a) contract; all six saved networks, full partitions and malformed-input/refusal controls; 600 seconds.

/home/ubuntu/workspace/hponas/program_operations/scientific_gap_repair.py references

SCI-02/REFERENCES: exact transformed Gaussian identities, deterministic controls and prospective wallet uncertainty formulas; zero observations or chains; 300 seconds.

/home/ubuntu/workspace/hponas/program_operations/scientific_gap_repair.py audit

SCI-02/AUDIT: all companion source/output hashes, coverage and adverse-result preservation; altered-evidence refusal; 300 seconds.

## SCI-03 certified evaluation and optional installed delivery

Reviewed plan: docs/program/SCIENTIFIC_DELIVERY_2026_10_25.md.
Exact fixed operations (each requires its active stage and a single-use manifest):

| Command | Bound and purpose |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/scientific_delivery.py wallet | 600 seconds; all three frozen pairs, outward population bounds, analytic/refusal controls; zero fits or samples |
| /home/ubuntu/workspace/hponas/program_operations/scientific_delivery.py delivery | 300 seconds; offline optional wheel build/install and dependency/origin checks |
| /home/ubuntu/workspace/hponas/program_operations/scientific_delivery.py verify | 600 seconds; installed saved-artifact roster and wallet partition replay |
| /home/ubuntu/workspace/hponas/program_operations/scientific_delivery.py audit | 300 seconds; independent exact aggregation, identities and false-evidence controls |

One CPU/thread, no GPU/network/services, 2-GiB RSS and 64-MiB outputs per operation.
The optional hponas-scientific-checks distribution has separate qualification;
it changes no accepted core code or failed historical outcome. Every manifest
pins inputs before launch. A consumed failed allocation requires a reviewed
successor, not an automatic retry. No global permissions or deployments.

SCI-03 defect-only successor after saved-wrapper schema refusal:
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v2.py wallet2
uses the same 600-second allocation and frozen six models. The old operation is
consumed FAIL. Remaining delivery/verify/audit commands use the same v2 executable
with the single documented operation; their manifests bind that exact runner.

SCI-03 priority-conversion defect successor (old allocations retained FAIL):
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v3.py wallet3
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v3.py delivery
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v3.py verify
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v3.py audit
The same reviewed operation bounds apply. Only non-acceptance heap-priority
conversion changed in wallet; all exact bound calculations remain unchanged.

SCI-03 delivery resource-accounting review uses these exact prospective commands:
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v4.py delivery
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v4.py verify
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v4.py audit
Owned output uses lstat sizes without following directory links. Immutable linked
runtime/dependency files are separately hashed inputs, not new outputs. All
wall/RSS/output limits and the source/receipt integrity requirements remain.

SCI-03 offline metadata discovery successor, same allocation bounds:
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v5.py delivery2
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v5.py verify
/home/ubuntu/workspace/hponas/program_operations/scientific_delivery_v5.py audit
Dist-info directories are copied for resolver discovery; numerical payloads stay
read-only linked and hash-bound. Full offline dependency resolution remains.

## PAR-01 CPU/GPU extension operations (26 October 2026)

Reviewed design: docs/program/PARALLEL_EXECUTION_EXTENSION_2026_10_26.md.
These fixed operations use at most four CPU cores, one numerical thread per
worker, no GPUs and 300 seconds per process with 8 GiB owned-RSS guard.
Exact inputs and runner hashes are recorded before execution; every attempt
keeps its logs and receipt. No scientific campaign or global rule change.

| Exact command | Purpose |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/parallel_ops.py resources | Fixed resource contract tests |
| /home/ubuntu/workspace/hponas/program_operations/parallel_ops.py executors | Persistent isolated CPU workers and executor compatibility |
| /home/ubuntu/workspace/hponas/program_operations/parallel_ops.py build | Four-pass current LaTeX manual in a fresh evidence directory |

/home/ubuntu/workspace/hponas/program_operations/parallel_ops.py study
PAR-01/STUDY: fixed parallel endpoint, declared evaluation and vector regression roster; same 300-second/four-CPU/no-GPU bound.

/home/ubuntu/workspace/hponas/program_operations/parallel_ops.py population
PAR-01/POPULATION: fixed PBT/PB2/BG-PBT, checkpoint and generational transfer controls; same four-CPU/no-GPU 300-second bound.

/home/ubuntu/workspace/hponas/program_operations/parallel_ops.py adapter
PAR-01/POPULATION: caller-adapter parallel and retained regression controls; four CPUs, no GPU, 300 seconds.

/home/ubuntu/workspace/hponas/program_operations/parallel_ops.py methods
PAR-01/CONFORMANCE: fixed real-method replica and concurrent vector routes; four CPUs, no GPU, 300 seconds.

/home/ubuntu/workspace/hponas/program_operations/parallel_hardware.py
PAR-01/HARDWARE: no arguments. Reviewed hardware-manifest.json selects idle
physical GPUs 1 and 3 by UUID; admission refuses other compute jobs. At most
four CPUs, two GPUs, 8 GiB owned RSS and 600 seconds. Tiny tensor references,
serial/GPU BG-PBT comparisons, CPU-portable restore and injected CUDA OOM.
No broad scientific campaign, service deployment, network or global rule edit.

/home/ubuntu/workspace/hponas/program_operations/parallel_ops.py ray
PAR-01/HARDWARE: one owned local Ray cluster, two logical CPU workers,
no GPUs, 300 seconds, 8 GiB owned RSS; no external service or network.
/home/ubuntu/workspace/hponas/program_operations/parallel_ops.py streaming
PAR-01/HARDWARE: retained streaming and cancellation regressions; same bounds.

/home/ubuntu/workspace/hponas/program_operations/parallel_ops.py audit-controls
PAR-01/AUDIT preparation: historical-source qualification bypass counterexamples and existing GAP trace controls; same fixed development limits.

/home/ubuntu/workspace/hponas/program_operations/parallel_audit.py
PAR-01/AUDIT: no arguments. Reconstructs all eleven bounded operation receipts,
immutable manifests, runner versions, actual CPU/GPU method coverage, zero-skip
XML results and built-manual text. Refuses stale/missing/tampered evidence with
negative controls. One CPU, no GPU/network, zero fitting; 300-second intended
bound. Does not issue scientific acceptance or allocate PAR-QUAL-01 campaigns.

## PAR-QUAL-01 admission

`/home/ubuntu/workspace/hponas/program_operations/parallel_calibration.py`
accepts no arguments. A reviewed calibration-manifest.json and fresh development,
installed-source, guard and protocol reconstructions are mandatory. Exactly one
complete current calibration; at most 24 CPU slots, 64 GiB owned RSS, no GPU,
2700 seconds internally and 2850 seconds under the independent descendant guard.
Disk admission/stop bounds are 32/16 GiB. Once-only output, no automatic retry,
no full scientific campaign. Manifest/driver review:
docs/program/evidence/2026-10-26/parallel-admission-01/.

`/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-qualification-run-01/run_controls.py`
accepts no arguments. Three serial controller failure/refusal groups, at most
300 seconds each, one CPU, no GPU, temporary synthetic fixtures, no campaign.
Exercises supervisor evidence ordering, raw worker-return witnesses and refusal
to bypass any unfinished master stage. Retains once-only control receipts.

## PAR-QUAL-01 callable compatibility repair

Reviewed successor manifests and driver review are under
docs/program/evidence/2026-10-26/parallel-repair-01/. Original PAR-01 inputs
are archived there before changes. These operations require active
PAR-QUAL-01/PREPARE and accept only the exact arguments shown.

| Exact command | Purpose and bounds |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/parallel_repair_ops.py population | Inherited parallel population/recovery roster plus callable regressions; four CPUs, no GPU, 300 seconds, 8 GiB owned RSS |
| /home/ubuntu/workspace/hponas/program_operations/parallel_repair_ops.py build | Four-pass current LaTeX manual, 300 seconds per process, same CPU/RSS bounds |
| /home/ubuntu/workspace/hponas/program_operations/parallel_repair_hardware.py | Entire inherited two-GPU roster plus buffer-only student/CPU teacher gradient test; idle physical GPUs 2 and 3 selected by UUID, four CPUs, 600 seconds, 8 GiB owned RSS |

Hardware admission refuses any existing compute job on either selected device.
No scientific allocation, external service, download or global permission change.
Original failure and source-specific audit receipts remain immutable.


## PAR-QUAL-01 repaired-source successor 02

The callable compatibility repair is verified on CPU and actual GPUs. Admission01
remains consumed FAIL. Successor02 preserves all scientific criteria, 17 campaigns,
five gates, and the final 27-clause audit. Preparation operations require reviewed
per-operation manifests, current source and active PAR-QUAL-01/PREPARE. They accept
only these fixed arguments, retain once-only receipts, and never launch a campaign.

| Exact command | Fixed operation and bounds |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py controls | Four serial supervisor/return/completion/transaction control groups, 300 seconds each; controller reconstruction 300 seconds; one CPU, no GPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py review-admission | Historical input and repair reconstruction with four damaged-evidence refusals; development/install/guard reconstruction; 300 seconds each, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_calibration_v2.py | One complete source-bound calibration; 24 CPU slots, no GPU, 64 GiB owned RSS, 2700/2850-second inner/outer bounds, 32/16-GiB disk guards; no retry |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py verify-calibration | Independent calibration reconstruction, 300 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py prepare-descendant | Exact historical Empty-handler mutation and complete current test selection, 300 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py run-descendant | One reviewed timeout/cleanup control; at most 24 CPU slots, 1650-second guard plus 30-second runner allowance, no GPU, no scientific campaign |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py verify-descendant | Exact -24 worker witness and clean descendants, 300 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py reconstruct-admission | Complete independent prerequisites, 300 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py audit-preflight | Six independent nonterminal examiner groups, 300 seconds each, 1900 seconds total, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py audit-review | Isolated close/reopen, publication, namespace and source-binding controls; 600 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_ops.py review-service | Two fixed refusal/review processes, 300 seconds each, one CPU; no service launch |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-admission-02/run_gap_program.py | Reviewed no-argument user service hponas-parallel-program-20261026-02; at most 68000 seconds; one prospective 17-campaign allocation then final independent audit |

The durable service starts only after admission passes. Restart=no and
KillMode=control-group apply. TimeoutStopSec=330 allows the bounded 300-second
stop-state reconstruction to restore prepared authority journals after their
owners stop. Recovery refuses live owners and corrupt preimages before writes;
it never retries consumed science. Qualification and final-audit publication
remain separate. Managed host-service approval is requested for this exact
reviewed launcher; no broad global allow rules, network, deployment or git action.

Admission review import-path successor (original failure retained):
/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-admission-02/review_admission_v2.py
Two unchanged review children, 300 seconds each, one CPU/no GPU; adds only the repository PYTHONPATH root before independent historical/repair/install reconstruction. No campaign or automatic retry.

Final-audit isolated-fixture review successor (original refusal retained):
/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-final-audit-01/run_review_v2.py
One CPU, no GPU, 600 seconds; fixes only the synthetic completed-stage evidence setup, tests candidate/final guidance recovery, and reviews exact current status rendering. All six rehearsal examiner bodies and scientific criteria remain unchanged.

Descendant preflight interpreter repair (no target had started):
/home/ubuntu/workspace/hponas/program_operations/parallel_descendant_v2.py
The original target and full 107-test selection stay unchanged. The system interpreter owns pidfd signalling; scientific children retain their frozen interpreter. One target, 1066-second independent guard plus 30-second wrapper allowance, no GPU/network/campaign/retry. Original refused wrapper remains recorded.

Audit review binding refresh after the additive interpreter repair command:
/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-final-audit-01/run_current_review.py
One CPU, no GPU, 600 seconds; preserve the prior review and exact old runbook, reexecute all 26 review controls, and bind successor driver review paths. No scientific source, examiner criterion or completed rehearsal change.


## PAR-QUAL-01 affinity successor 03

The preceding service refused wide-affinity finite preparation before allocation.
Fresh qualification03/audit02 paths preserve its outputs. Freeze alone narrows
to one CPU before writes; the service parent keeps exactly 24 CPU slots. Passing
current-source calibration, descendant, development and installation evidence
are reconstructed, not repeated. Scientific criteria and caps are unchanged.

| Exact command | Bounded preparation or execution |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v3.py affinity | Four real runtime admission/refusal controls; parent 24 CPUs, children one CPU after admission, no GPU computation, 300 seconds |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v3.py controls | Four controller/recovery groups at 300 seconds each plus 300-second reconstruction; one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v3.py reconstruct-admission | Current prerequisite reconstruction, 300 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v3.py audit-preflight | Six 300-second finite examiners, 1900 seconds total, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v3.py audit-review | Close/reopen/publication/runtime controls, 600 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v3.py review-service | Fixed service refusals and binding review, 300 seconds each, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v3.py record-ready | Register reviewed admission and regenerate/check master, 1900 seconds, one CPU |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-launch-03/run_gap_program.py | Once-only reviewed user service hponas-parallel-program-20261026-03, 68000-second ceiling, 60870 seconds summed step caps |

Preparation requires current source, the active PREPARE stage, exact manifests
and fresh outputs. No campaigns are allocated by preparation. Service execution
retains 24-CPU/64-GiB/no-GPU, 32/16-GiB disk guards, Restart=no, control-group
cleanup and 330-second stop recovery. Only finite freeze admission narrows the
service child. Final completion still requires all 17 campaigns, five gates and
the final 27-clause audit; no retry, new scientific claim or global rule change.


## PAR-QUAL-01 critical controller coverage repair

The interrupted qualification03 remains INCONCLUSIVE with 21 unproved critical
Study.run survivors. Its stopped service released the source freeze; original
raw results and publication refusal are retained. The reviewed bounded repair
is docs/program/evidence/2026-10-26/parallel-critical-coverage-repair-01/coverage-review.md.

Exact one-time transition:
/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-critical-coverage-repair-01/register_repair.py

It refuses live predecessors/frozen source, archives authority and guidance,
installs two reviewed single-CPU controller test files, extends the fixed
test-study roster and registers repair preparation. No campaign, service, GPU,
network or git action. Six existing governance checks have 300-second limits.
The unchanged exact test-study command executes the added tests under its
existing one-CPU/no-GPU/300-seconds-per-process bounds.


Exact one-time critical-branch diagnostic:
/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-critical-coverage-repair-01/run_diagnostic.py

The bound diagnostic-review.json selects 28 exact retained transformations and
two clean baselines. Fresh children receive 15 seconds each, one CPU/no GPU;
the identity-aware independent guard permits 600 seconds and 4 GiB owned RSS.
Inputs/source are verified before and during execution. No campaign, automatic
retry, service, network, git or source edit. Surviving changes remain findings.


## PAR-QUAL-01 current coverage-repair verification

The interrupted qualification03 and all old manifests remain immutable.
Reviewed manifests and driver transformations are under
docs/program/evidence/2026-10-26/parallel-critical-coverage-repair-01/.
These commands require active EXECUTE repair and unfrozen scientific source.

| Exact command | Fixed verification |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/parallel_coverage_ops.py executors | Inherited worker/executor/control roster; four CPUs, no GPU, 300 seconds, 8 GiB |
| /home/ubuntu/workspace/hponas/program_operations/parallel_coverage_ops.py study | Actual parallel declared scalar/vector Study roster; same limits |
| /home/ubuntu/workspace/hponas/program_operations/parallel_coverage_ops.py methods | All inherited method routes and same-seed replica controls; same limits |
| /home/ubuntu/workspace/hponas/program_operations/parallel_coverage_ops.py population | Inherited PBT/PB2/BG-PBT and transfer roster; same limits |
| /home/ubuntu/workspace/hponas/program_operations/parallel_coverage_ops.py build | Four-pass current manual build in a new evidence directory; 300 seconds per process |
| /home/ubuntu/workspace/hponas/program_operations/parallel_coverage_hardware.py | Full inherited CUDA roster; physical GPUs 2 and 3 by UUID, four CPUs, 600 seconds, 8 GiB |

Hardware admission refuses existing compute processes on either selected GPU.
No scientific allocation, network, deployment, git mutation or global allow-rule
change. New-source results supplement the exact historical results; they never
retag them. The remaining fourteen fixed operations retain their existing commands.


## PAR-QUAL-01 coverage successor qualification04

Reviewed plan: docs/program/evidence/2026-10-26/parallel-admission-03/successor-review.md.
All operations require their exact current manifests and fresh output paths.
They remain under EXECUTE repair with PREPARE complete and source unfrozen.
No preparation operation allocates scientific campaigns or retries a result.

| Exact command | Bounds and purpose |
|---|---|
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py affinity | Four real 24-CPU parent/single-CPU freeze controls; 300 seconds, no GPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py controls | Four serial controller groups at 300 seconds each, then 300-second reconstruction |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py review-admission | Historical/current evidence and installation/guard reconstruction; 300 seconds each |
| /home/ubuntu/workspace/hponas/program_operations/parallel_calibration_v3.py | One complete calibration; 24 CPUs, 64 GiB, no GPU, 2700/2850-second inner/outer limits, 32/16-GiB disk guards |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py verify-calibration | Independent calibration/worker-return reconstruction; one CPU, 300 seconds |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py prepare-descendant | Match exact retained mutation and all current selected tests; one CPU, 300 seconds |
| /home/ubuntu/workspace/hponas/program_operations/parallel_descendant_v3.py | One exact timeout/cleanup control; scheduler-derived guard at most 1650 seconds plus 30-second wrapper; 24 CPUs, 64 GiB, no GPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py verify-descendant | Require exact -24 witness and clean owned exit; one CPU, 300 seconds |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py reconstruct-admission | Full independent admission; one CPU, 300 seconds |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py audit-preflight | Six nonterminal examiner groups; 300 seconds each, 1900 total, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py audit-review | Close/reopen/publication/runtime controls; 600 seconds, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py review-service | Service refusal and binding checks; 300 seconds each, one CPU |
| /home/ubuntu/workspace/hponas/program_operations/parallel_qualification_v4.py record-ready | Register reviewed admission and governance checks; 1900 seconds, one CPU |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-launch-04/run_gap_program.py | Once-only reviewed host service; 17 campaigns/five gates then final 27-clause audit; 68000-second ceiling |

The service refuses an occupied identity or unavailable user bus before writing
launch outputs. Managed host permission remains required when the sandbox blocks
user-service access. Restart=no, KillMode=control-group and TimeoutStopSec=330.
The scientific freeze keeps all original criteria, 36000/36900-second V03 limits,
24 CPUs/eight high-memory jobs/64 GiB/no GPU and 32/16-GiB disk bounds. No network,
deployment, git mutation, global permission broadening or automatic retry.


Coverage successor admission import-root repair (original failed receipt retained):
/home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-admission-03/run_review_admission_v2.py

No arguments; two unchanged reviewer bodies, one CPU/no GPU, 300 seconds each.
Adds only the repository root to child PYTHONPATH before reconstruction.
Requires exact current manifest, retained import failure and fresh output path.
No scientific allocation, criterion change or automatic retry.


## PAR-01 reviewed publication04 preparation

This is documentation follow-through under GAP-01/FINAL-AUDIT, after the
already-adopted PAR-QUAL-01 qualification04. Plan and prospective review:
docs/program/evidence/2026-10-26/parallel-publication-refresh-04/plan.md.
No new scientific stage, campaign, criterion or unsupported claim is added.

| Exact command | Bounds and prerequisite |
|---|---|
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-publication-refresh-04/run_preparation.py | One CPU, no GPU/network; fixed six-step refusal/rollback/render review and labelled layout rehearsal; five 300-second review children and one 2200-second layout child; requires current manifest and active qualification freeze |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-publication-refresh-04/run_continuation.py | Once-only host waiter; all three predecessor publication services stopped; 68000 seconds waiting, 2200 building, 9000 publication, 80000-second service ceiling; no restart or scientific retry |

The waiter launches no publication before actual successful qualification04,
the independent 27-clause final audit and the stopped scientific service.
The final build changes only separate generated chapters; publication journals
guidance and authority preimages, then runs the six governance checks and final
closure guard. Any failure retains evidence and refuses false completion.
Managed approval for the exact host command remains authoritative; no global
permission broadening, external publication, deployment or git action.


## GAP-01 terminal audit affinity repair

Qualification04 passed all seventeen campaigns and five gates. Audit03 terminal
reconstruction refused inherited 24-CPU affinity before the final audit started.
The failure and publication04 refusal remain immutable. The successor retains
qualified scientific source and performs no campaign retry. Reviewed plan:
docs/program/evidence/2026-10-26/parallel-audit-affinity-repair-01/plan.md.

| Exact command | Bounds and purpose |
|---|---|
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-audit-affinity-repair-01/run_operation.py affinity | 300 seconds; 24-CPU admission control then single-CPU children; no GPU/network/scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-audit-affinity-repair-01/run_operation.py preflight | 1900 seconds; one CPU; no GPU/network/scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-audit-affinity-repair-01/run_operation.py review | 600 seconds; one CPU; no GPU/network/scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-audit-affinity-repair-01/run_operation.py terminal | 650 seconds; one CPU; no GPU/network/scientific allocation |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-audit-affinity-repair-01/run_operation.py audit | 6000 seconds; one CPU; no GPU/network/scientific allocation |

Each operation is once-only and source/input bound. The seven audit groups,
27 clauses, protocol/candidate controls and scientific thresholds are unchanged.
Final publication requires actual audit completion and reviewed document controls.


## PAR-01 terminal publication follow-through

After qualification and the independent audit pass and their service stops, these once-only commands complete documentation under GAP-01/FINAL-AUDIT. No scientific source, criteria or historical evidence change.

| Exact command | Bound |
|---|---|
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-publication-refresh-05/run_build.py | One CPU, no GPU/network; five-pass manual build and PDF text/info checks, 300 seconds and 8 GiB address space per process |
| /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-26/parallel-publication-refresh-05/run_publication.py | One CPU, no GPU/network; journalled status/manual reconciliation, six governance checks and final closure guard; 300 seconds per check |


## RL-LQR-01 exact operations (27 October 2026)

The reviewed manifest is `docs/program/RL_LQR_EXTENSION_2026_10_27.md`.
Each fixed operation binds its extension inputs, uses at most four CPU cores,
16 GiB owned host RSS, a 2 GiB output cap and a 4 GiB free-disk floor.
The runtime overlay is independent of the accepted core environment.

| Exact command | Bound and purpose |
|---|---|
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py runtime` | 600 seconds; download/install four missing RLlib wheel families into a local overlay; imports and lock |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py oracle` | 300 seconds; fixed reference/environment tests; no learning |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py learner` | 600 seconds; at most two 512-transition SAC fits and checkpoint controls |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py joint` | 3600 seconds; eight configurations times two seeds plus two final fits; 4096 transitions each; two CPU workers |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py joint-replay` | 600 seconds; read-only completed-Study replay of the retained 18 fits, objective dispatch forbidden, zero new transitions |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py hardware` | 600 seconds; two 512-transition fits on two distinct GPUs |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py build` | 600 seconds; guide/manual build; no learning |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py audit` | 600 seconds; replay saved results and source bindings; no training |
| `/home/ubuntu/workspace/hponas/program_operations/rl_lqr_ops.py master-audit` | 600 seconds; GAP-01/FINAL-AUDIT reconciles unchanged core qualification, original clauses and completed RL-LQR evidence, with false-completion control; zero new training |

## Five-state LQR formulation and BG-PBT readiness (RL-LQR-02)

Reviewed scope: `docs/program/LQR5_BG_PBT_FEASIBILITY_2026_10_27.md`.
These operations use one CPU, no GPU/network or Ray cluster, 300 seconds,
8 GiB owned RSS, 128 MiB outputs and a 4 GiB disk floor. Training allocation
is zero. Each operation requires its active master stage and exact manifest;
the runner binds and archives all input source and owns descendant cleanup.

| Exact command | Purpose |
|---|---|
| `/home/ubuntu/workspace/hponas/program_operations/lqr5_ops.py preflight` | Fixed reference, conditional search and actual RLlib network tests; no optimizer training |
| `/home/ubuntu/workspace/hponas/program_operations/lqr5_ops.py audit` | Replay preflight bindings/results and reject false cost/support/training evidence |
| `/home/ubuntu/workspace/hponas/program_operations/lqr5_ops.py master-audit` | Reconcile unchanged qualified core, original gap closure and limited five-state readiness scope |

## Five-state SAC BG-PBT implementation (RL-LQR-03)

The reviewed plan is `docs/program/LQR5_SAC_BGPBT_IMPLEMENTATION_2026_10_27.md`.
Each operation requires its active master stage and source-bound manifest under
`docs/program/evidence/2026-10-27/rl-lqr-03`. Successful scientific allocations
are once-only; engineering repair attempts retain every prior receipt. Three
CPU cores (coordinator plus two one-thread workers), 16 GiB owned RSS, 4 GiB
outputs and 8 GiB disk headroom are hard limits. The successor reviewed in
`docs/program/LQR5_SAC_BGPBT_REVIEW_REPAIR_2026_10_27.md` permits shared GPUs:
two devices with at least 4 GiB free each, a 1 GiB Torch allocator cap and a
2 GiB observed process-memory cap per worker. No network is used.

| Exact standalone command | Fixed operation |
| --- | --- |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py engineering` | Adapter, conditional GP, distillation, transactional recovery and actual CPU concurrency tests; 600 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py repair-engineering` | Original roster plus order-independent region, objective-based candidate SAC, best checkpoint, shared memory admission and replay; 600 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py procedure-check` | Three complete paired tuning procedures, seeds 9211–9213; at most 233,472 transitions, 57,408 SAC and 768 distillation updates; 1,800 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py selection-reconciliation` | Correct zero-update copy attribution from saved checkpoints, preserving identical costs and actors; four focused regressions and report reconstruction, zero training, 600 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py device-repair` | Eight adapter/device tests; direct assigned-device learner setup without Ray auto-init; ≤1,024 transitions, 256 SAC and 64 distillation updates, 300 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py calibration` | Two fixed 8,192-transition learning curves and prospective budget freeze; 1,800 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py search` | Four-member/four-segment BG-PBT plus matched-work static random-search baseline; 1,800 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py confirmation` | Three reserved fresh paired seeds for frozen static selected configurations; 1,800 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py hardware` | Shared two-GPU SAC, Bayesian rate/architecture proposals, compatible/distilled descendants and cross-device restore; ≤2,048 transitions, 512 SAC and 64 distillation updates, 600 seconds |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py documentation` | Build successor LaTeX manual and verify rendered statements; zero training |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py hardware-documentation` | After GPU qualification, rebuild the manual with current hardware evidence before final audits; zero training |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py audit` | Independent scores, proposals, ledger, checkpoints, selection, confirmation and hardware; zero training |
| `/home/ubuntu/workspace/hponas/program_operations/sac_bgpbt_ops.py master-audit` | Final master reconciliation after all required extension stages; zero training |

The SAC implementation is an optional companion; public LocalBGPBT retains its
qualified finite-model contract. The listed allocations are bounded experiments.

Run these commands exactly. Missing managed network/socket/GPU permission is
requested only for the concrete operation. No global allow rules are broadened.
Failed attempts remain immutable and require a reviewed successor; successful
training allocations cannot automatically repeat. This companion supports
replay-based Gaussian/twin-critic distillation followed by SAC; it is not the
paper's on-policy PPO transfer. Hardware uses a two-worker ready barrier.

## Ten-state horizon-thirty extension (RL-LQR-04)

Reviewed scope: docs/program/LQR10_H30_STUDY_2026_10_27.md. Two single-thread
CPU workers plus a coordinator; 16 GiB owned RSS, 8 GiB outputs and 8 GiB disk
headroom. No network or idle-GPU requirement. Source-bound manifests and every
attempt are retained under docs/program/evidence/2026-10-27/rl-lqr-04.

| Exact standalone command | Fixed operation |
| --- | --- |
| /home/ubuntu/workspace/hponas/program_operations/lqr10_ops.py engineering | Fourteen reference/evaluation/learner/recovery tests; at most 1024 transitions, 256 SAC and 64 distillation updates; 600 seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr10_ops.py study | Three paired searches, 466944 transitions, 115776 SAC and 768 distillation updates; 1024 validation and 16384 final test paths; 3600 seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr10_ops.py audit | Reconstruct oracle, scores, selected artifacts, work and paired controls; zero training; 900 seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr10_documentation.py | Build versioned successor LaTeX manual from frozen completed study; source-bound inputs, no training or network; each build command at most 120 seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr10_ops.py master-audit | Reconcile expanded master and reject false completion; zero training; 600 seconds |

Successful allocations cannot repeat. Failed engineering attempts require a
documented defect repair and refreshed source binding. Learning outcomes are
reported numerically; successful execution does not establish optimal learning.

## Multi-action ten-state extension (RL-LQR-05)

Reviewed scope: docs/program/LQR_MULTI_ACTION_STUDY_2026_10_27.md.
Four single-thread CPU workers and coordinator;16 GiB RSS,16 GiB outputs,
8 GiB disk floor. No GPU/network required. Immutable predecessor evidence.

| Exact standalone command | Fixed purpose and bound |
| --- | --- |
| /home/ubuntu/workspace/hponas/program_operations/lqr_multi_ops.py engineering | Vector reference, actor/critic, replay/transfer isolation;4096 transitions,1024 SAC,128 distillation maximum;600 seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_multi_ops.py study | Twelve paired studies across2--5 actions;1,867,776 transitions,463,104 SAC,3,072 distillation updates;5400 seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_multi_ops.py audit | Full artifact/reference/work/selection reconstruction;zero training;1800 seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_multi_documentation.py | Frozen-result guide and successor LaTeX manual;zero training;120 seconds per build command |
| /home/ubuntu/workspace/hponas/program_operations/lqr_multi_ops.py master-audit | Final expanded-master reconciliation;zero training;600 seconds |

Each operation is active-stage and source bound. Successful study work cannot
repeat. Failed engineering attempts retain receipts and require defect repair.

## Scalar-state diagnosis (RL-LQR-06, 28 October 2026)

Reviewed scope: docs/program/LQR_SCALAR_STATE_DIAGNOSTIC_2026_10_28.md.
Three matched cases, three paired seeds each. Four CPU workers and coordinator;
16GiB owned RSS/output caps;8GiB disk floor. No GPU/network or campaign reuse.

| Exact standalone command | Fixed operation and bound |
| --- | --- |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scalar_ops.py engineering | Scalar/vector/padded references and learner contracts;4096 transitions,1024 SAC,128distillation max;600seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scalar_ops.py study | Nine paired procedures;1,400,832transitions,347,328SAC,2,304distillation;5400seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scalar_documentation.py | Source-bound result guide/LaTeX manual and decomposition checks;zero training;120seconds per build command |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scalar_ops.py audit | Reconstruct396tasks and all holdouts, work and source;zero training;1800seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scalar_ops.py master-audit | Expanded-master final reconciliation;zero training;600seconds |

The study is once-only. Failed engineering attempts require documented repair
and fresh source binding; every scientific outcome remains in evidence.

## Scalar failure tracing (RL-LQR-07, 28 October 2026)

Reviewed plan: docs/program/LQR_SCALAR_FAILURE_TRACE_2026_10_28.md.

| Exact standalone command | Bound |
| --- | --- |
| /home/ubuntu/workspace/hponas/program_operations/lqr_debug_ops.py diagnose | Twelve saved checkpoints, zero training, one CPU, 900seconds, 8GiB RSS, 1GiB output, 8GiB disk floor. Successful allocation cannot repeat. |

| /home/ubuntu/workspace/hponas/program_operations/lqr_debug_audit.py audit | Independent exact identities, finite differences, 396 artifact rows; zero training, 900seconds, one CPU, 8GiB RSS. |
| /home/ubuntu/workspace/hponas/program_operations/lqr_debug_audit.py master-audit | Final program reconciliation; zero training, 600seconds, one CPU, 8GiB RSS. |

## Scalar learner repair (RL-LQR-08, 28 October 2026)

Reviewed plan: docs/program/LQR_SCALAR_REPAIR_2026_10_28.md.
At most four one-thread CPU workers plus coordinator,16GiB RSS,8GiB outputs,8GiB disk floor. No GPU/network. Successful allocations cannot repeat.

| Exact standalone command | Fixed bound |
| --- | --- |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py engineering | Mathematical, continuation and replacement tests;2048transitions/512SAC/128imitation/128critic-only;600seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py learner | Nine fixed learners;73728transitions/17856SAC and2048separate exact-Q actor updates;2400seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py review | Freeze selected repair and next allocation;zero training;60seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py handoff | Six transfers and three donor continuations;9216transitions/2304SAC/1536imitation/1536critic-only;1200seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py confirm | Six fresh fixed learners;49152transitions/11904SAC;1800seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py joint | Conditional allocation frozen at REVIEW before execution;3600seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py audit | Independent source/work/evidence audit;zero training;600seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py master-audit | Final master and false-completion audit;zero training;600seconds |

| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py handoff-engineering | Donor/actor preservation and gradient-aware transfer tests;zero transitions,16imitation/16critic-only;300seconds |

| /home/ubuntu/workspace/hponas/program_operations/lqr_repair_ops.py joint-engineering | Complete fake-learner scheduler, rejection, historical selection and exact work tests;zero training;300seconds |

## Dimensional SAC scaling (RL-LQR-09, 28 October 2026)

Reviewed plan: docs/program/LQR_DIMENSION_SCALING_2026_10_28.md. Four one-thread CPU workers plus coordinator;16GiB RSS,8GiB output,8GiB disk floor,no GPU/network. Source-bound successful allocations are once-only.

| Exact standalone command | Fixed scope and cap |
| --- | --- |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py engineering | References,terminal gradients,symmetry,checkpoint continuation;4096transitions/1024SAC;600seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py actions | One state,actions5--10,two methods/two seeds;196608transitions/47616SAC;2400seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py review | Review action results;zero training;60seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py states | Ten coupled states,actions5--10,two methods/two seeds;196608transitions/47616SAC;3600seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py freeze | Seal method choices and prospective confirmation;zero training;60seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py confirm | Twelve cases,two methods,three fresh seeds;589824transitions/142848SAC;7200seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py audit | Independent scores/references/ledgers/source and learned-controller audit;zero training;1800seconds |
| /home/ubuntu/workspace/hponas/program_operations/lqr_scale_ops.py master-audit | Expanded master completeness and false-completion controls;zero training;600seconds |

## Summary-only publication checks (28 October 2026)

| Exact standalone command | Scope |
| --- | --- |
| /home/ubuntu/workspace/hponas/program_operations/publication_ops.py checks | Publication index guard and reviewed archive-independent regression roster; two serial processes, 300 seconds each, two CPU slots with one numerical thread, no GPU or scientific training; logs stay under ignored .local-archives. |

Historical operations that bind raw evidence require restoration of the local archive. Publication checks do not substitute for those scientific audits. Raw evidence, generated checkpoints and LFS pointers must not be committed. See docs/ARTIFACT_STORAGE.md and docs/publication-policy.json.
