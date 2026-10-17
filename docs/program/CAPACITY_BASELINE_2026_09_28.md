# Capacity baseline — CAP-01 preparation

CAP-01 is in the master program. This is a read-only inventory and budget design, not a pilot or an allocation of resources. The complete feasible schedule remains **blocked on STAT-02 and D-PROTOCOL**. A dependency date cannot substitute for task identities, pilot observations, a funded replication envelope or an assigned operator.

## What is measured

The [inventory](evidence/2026-09-28/cap-01/inventory.json) records Linux x86_64/glibc 2.35, 256 visible logical CPUs, memory availability and the existing bounded PPO receipts. Its sandboxed GPU query failed; a separate permitted [host query](evidence/2026-09-28/cap-01/host-gpu-snapshot.json) records four visible NVIDIA devices and momentary utilization. Neither result reserves GPU capacity. No other project's processes or allocations are changed.

The retained smoke examples cost 16.65–23.45 seconds per objective call. The retained V14 integration example completed in 25.22 seconds including its declared workflow. These are 128-step, tiny-network CPU smoke/integration examples on an earlier source. They are **not** 100K-step training estimates, independent pilot observations, uncertainty estimates or evidence of attainable power. Compilation, environment length, model size and optimizer overhead prevent multiplying these numbers by a step ratio to obtain a credible campaign forecast.

## Executable envelopes already recorded

| Work | Current envelope | Outcome at limit |
|---|---|---|
| Local deterministic specification repairs | Two workers; test selection capped at 600 seconds; independent reference probes 300 seconds | Preserve failures/timeouts; no acceptance claim |
| PKG-01 installation verification | Fresh Python 3.12/3.13 Linux CPU environments; 2,400 seconds overall; planned downloads below 6 GiB; bounded Ray/PPO installation smoke | Preserve resolver/build/runtime logs and report the unverified configurations |
| V03-03 full mutation acceptance | At most four workers and six wall-clock hours on frozen source/profile | INCONCLUSIVE with full partial inventory, never synthetic kills |
| STAT-02 pilot and PPO-01 confirmation | Not allocated; task/design/certification and capacity remain prerequisites | Do not launch an unspecified campaign |

## How to derive the remaining program schedule

1. Resolve the claim/multiplicity decisions and freeze task IDs, measured-budget accounting, model/training envelope, scale bounds, candidate sample sizes and independent seed blocks. Define each study replicate and the exact number of task clusters.
2. Measure the independent real-workload pilot under the intended hardware and concurrency policy. Separate startup/compilation, active accelerator seconds, CPU seconds, queueing and elapsed time. Pilot performance data never enters confirmation.
3. Size each endpoint at its declared adjusted alpha and power target using its task/paired-block hierarchy and conservative variance bound. Report uncertainty and inability to attain power within the register's sample cap; do not weaken the target to fit available machines.
4. Compute the cost as the sum of measured study costs over task × paired block × arm, plus separate protected evaluations, audits and the single preregistered replication if permitted. Scheduling uses measured throughput under a specified reservation, not the visible GPU count. Name the operator, reservation window and replication owner before spending.
5. Put measured effort ranges and the longest dependency chain back into the master. Keep verification, acceptance and release decisions separate. Later tiers remain behind REL-01; they do not receive speculative calendar commitments.

The independent installation work continues now. CAP-01 is not marked complete because the final protocol design and pilot are still missing. This is an explicit dependency within the current master, not a proposed change of execution direction.
