# Crash recovery and current execution

This is recovery of the existing V03-03 and PKG-01 obligations. The source
digest remains `6422806522fe0a2d3f906e1083810023182600ebf691f2a446b016678024ffe7`.
All 558 registered evidence hashes and all 508 retained attempt-08 files match.
No validation process was running at inspection. Attempt 09 has a plan, but no
launch or host-baseline receipt. Attempt 08 remains INCONCLUSIVE with 7,034
killed, 470 surviving, 14 timed out and 1,026 unchecked mutations; its V16 PASS
does not establish mutation acceptance.

The maintained Study repair passed 14 focused checks and independently detected
all 70 selected progress/promotion survivors. The first broad baseline retained
42 failures: missing CMA-ES and downstream cases plus one explicit thread-setting
refusal. The second retained 2,837 passes, 25 failures, five setup errors and one
skip: 29 Ray startup failures/errors and the same thread-setting refusal. Neither
baseline is a campaign prerequisite PASS. The requested host rerun was aborted
before a receipt existed.

The crash removed the CMA-ES overlay, the Python 3.12/3.13 isolated environments,
the package tool and caches in `/tmp`. The main scientific environment survives;
its distribution manifest differs from attempt 08 only by the missing
`cmaes==0.12.0`. Restoration uses `.hponas-runtime/` for environments, downloaded
packages, caches and future mutation workspaces. This directory is ignored by
Git and outside the scientific source-digest inventory. Each future execution
still binds its exact source, dependencies and inputs; no interrupted campaign
is silently resumed or counted as complete.

The master had documentation and dependency gaps: its manual header said 1.45
while the register said 1.46, closed attempt 08 was described as running, the
second failed baseline was unregistered, and the latest installation step was
not a prerequisite of the final recheck/readiness. The recovery revision repairs
those gaps while retaining the exact earlier master and all failed evidence.

Execute the existing program in this order:

1. `V03-03/CRASH-RUNTIME-RECOVERY`: restore the pinned scientific dependency
   overlay and verify the complete runtime manifest. Recreate the isolated
   installation environments from retained manifests, recording any unavailable
   pinned input as an explicit recovery failure. Use the existing PKG-01 bounds:
   two CPU slots, 2,400 seconds for reconstruction, at most 6 GiB downloaded;
   installed verification retains its separate 900-second cap.
2. `V03-03/ATTEMPT08-REPAIR`: complete the exact copied non-slow baseline with
   `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, the restored overlay, live Ray
   sockets and the frozen deterministic test ordering. Retain source, data,
   dependency and start/end identities under the existing 900-second cap.
3. `PKG-01/ATTEMPT09-INSTALLATION`: rebuild the current wheel and rerun installed
   public checks and examples in the recovered isolated environments.
4. `V03-03/FINAL-RECHECK`: launch one fresh attempt 09 after the preceding
   receipts pass. The unchanged protocol 2.7 requires same-workspace calibration,
   four workers, a six-hour total cap, independent raw-outcome reconstruction and
   V16. Runtime/coverage feasibility remains an objective prerequisite; preserve
   every unresolved outcome and continue repair if acceptance is not established.
5. After complete mutation acceptance, continue the registered finite conformance,
   conditional pilot-readiness and governance refresh. Pilot allocation and
   release remain separate obligations. Human acceptance cannot replace evidence.
