# Fixed local program operations

12 October 2026. These commands implement the user's request to reduce repeated approvals for the authorized HPO-NAS repair program. Run the absolute executable and the single operation **exactly as written**. Do not prefix environment assignments, use a Python/shell wrapper, append flags, or chain commands. The helper sets the working directory, interpreter, numerical thread limits, test roster and unique output directory.

| Exact command | Work and writes | Bound |
|---|---|---|
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py status` | Reads the current master/register and source; prints the active step and blockers | Small local read |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py checks` | Regenerates program views and runs the six existing checks; retains logs/receipt | Six serial processes, at most 300 seconds each |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py test-study` | Fixed Study/evaluation/checkpoint/vector regressions, then owned local Ray streaming and declared-workflow verification | Two serial processes, 300 seconds each |
| `/home/ubuntu/workspace/hponas/program_operations/hponas_ops.py test-search` | Static whole-test collection check, then fixed searcher/GP/capability regression roster | Two serial processes, 300 seconds each |
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
mode runs the two named streaming/declared suites. Both retain XML, logs and a
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
