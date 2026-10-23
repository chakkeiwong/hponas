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
