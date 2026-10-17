# Attempt11 monitoring and closure recovery

Attempt11 is executing the existing `V03-03/FINAL-RECHECK` stage. The four-worker,
six-hour mutation campaign, protocol 2.7, frozen source and acceptance criteria
are unchanged. Monitoring and closure recovery belong to that stage; they do
not create a new scientific direction or authorize pilot spending.

The independent host observer records process ownership, worker CPU/RSS,
available memory, heartbeat age, raw abnormal exits and terminal receipts every
30 seconds. Its mutable observations are operational telemetry, not immutable
acceptance evidence. A heartbeat older than 90 seconds or owned RSS above 16 GiB
requests investigation. Those alert thresholds neither change campaign limits
nor automatically kill workers. The assistant investigates alerts and implements
repairs; the observer itself only records them. A sandbox's inability to see
host PIDs is not evidence of a crash.

Review found a deterministic defect in the registered controller's non-PASS
branch: its proposed closure and repair stages still use `ATTEMPT10` IDs already
present in the register. Candidate validation rejects the duplicate stages
before replacing the authority. The original branch, controller and all run
evidence remain preserved.

The separate `recover_failure_branch.py` driver can activate only after the
registered sequence has a terminal receipt for that exact duplicate-step error.
It checks source identity, original result bindings, recomputed V03 and V16,
and retained source; it then uses the controller's validated refresh transaction
with unique `ATTEMPT11-CLOSURE` and `ATTEMPT11-REPAIR` stages. Original campaign
outcomes remain unchanged. Its regression extracts and executes the actual
retained failure branch in memory, reproduces the duplicate rejection, validates
the repaired candidate against the complete register, verifies the next eligible
repair stage, and verifies refusal during active execution or accepted closure.

The run has not finished. Its live survivor counts are not a verdict. On closure,
the registered chain retains raw evidence and independently reconstructs the
frozen criteria. Accepted mutation evidence permits V01/V02/V14 and conditional
pilot-readiness review. A non-accepted result requires diagnosis and repair of
the demonstrated gaps. A genuine external dependency may stop execution only
after the combined whole-program audit verifies that no independent internal
work remains. The master program is incomplete.

Implementation and regression evidence:

- [Observer](evidence/2026-10-05/attempt11-monitor-01/monitor_attempt11.py)
- [Guarded recovery](evidence/2026-10-05/attempt11-monitor-01/recover_failure_branch.py)
- [Actual-branch regression](evidence/2026-10-05/attempt11-monitor-01/check_failure_recovery.py)
- [Regression result](evidence/2026-10-05/attempt11-monitor-01/recovery-regression.json)
