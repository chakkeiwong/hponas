# Five-state joint SAC BG-PBT companion

This optional companion searches **actor architecture, critic architecture,
actor learning rate and critic learning rate together**. It uses Ray RLlib
2.58's upstream SAC Torch learner and this repository's resource executor and
temporal BG-PBT Gaussian process. It does not change the finite-MDP
`hponas.LocalBGPBT` class. The predecessor readiness report remains historically
correct for that class.

The master work item is **RL-LQR-03**. Its dependencies and exact receipts live
in `docs/program/program.json`; `results-index.json` binds completed companion
stages. A stage may pass engineering checks while its learning comparison is
unfavorable. The final master audit cannot close while hardware is incomplete.

## Model and objective

Five coupled states, one continuous action, horizon eight, discount 0.99; the
observation includes remaining time. Actor and critic each have independently
chosen 2--4 hidden layers, each with 8--64 neurons and tanh activation. The two
critics use the same architecture specification with independent parameters and
targets. Actor and critic Adam rates are independently continuous in
`[1e-5, 1e-2]`, represented on log scale. Every hidden layer appears exactly once
in the RLlib encoder/head arrangement.

The deterministic-policy objective is discounted quadratic cost on the complete
8,192-path initial/noise law. The attainable Riccati optimum is
**3.2540811593967556** and zero-action cost is **3.889419041418345**. Every score
is checked against the quadratic performance-difference identity. Exact finite
scoring removes evaluation sampling error; training randomness remains. No
oracle action or Riccati gain enters SAC or distillation. The SAC loss includes
entropy regularization, whereas configuration selection uses the stated cost.

## Implemented behavior

The original pilot APIs below remain available for evidence replay. The repaired
`JointExplorer` and `population_search_v2` update trust-region state once per
round, use an objective surrogate plus random architecture proposals, and train
all proposed architecture/rate pairs with SAC before halving on actual cost.
Both methods select their best evaluated checkpoint. `procedure-check` runs
three complete paired searches, rather than duplicating static configurations.
The replay imitation warm-start followed by SAC is a bounded BG-PBT adaptation;
it does not reproduce the paper's annealed on-policy PPO transfer.

`SACMember` runs an upstream `SACTorchLearner` with explicit environment sampling
and uniform one-step replay: batch 128, replay capacity 32,768, 256 random warmup
transitions, one four-optimizer SAC update per four subsequent transitions,
target Polyak coefficient .005 and temperature rate .0003. It avoids starting
a Ray cluster for each small learner. This is a custom sampler around standard
RLlib SAC, not stock `SACConfig.build_algo()` execution.

`Explorer` uses the BG-PBT temporal mixed Matérn kernel for score improvements,
with time, starting cost and architecture context. Rates move in adaptive local
trust regions, with global restart after collapse. A generation proposes 64
new joint configurations and chooses four by UCB with pending-point variance.
This bounded proposal batch is a sample from the full conditional space, not
an exhaustive list of allowed architectures. The full space has
115,443,055,380,249 actor/critic architecture pairs, before continuous rates.

`population_search` runs four members for four equal training segments. After
segments one and three, the best member supplies a compatible copy to the worst
member and receives Bayesian rate changes. After segment two, an age-triggered
generation distills four different candidate architectures for 16 steps, keeps
two by recorded training-replay distillation loss and gives them 48 additional
steps. The two students replace the worst members. Teacher weights never change.
The Gaussian-policy KL and both soft-Q losses use training replay only; targets
are set to online critics and SAC Adam state is reset after a shape change.

All checkpoint state is explicit: actor, critics, targets, four Adam states,
temperature, target clock, replay, environment state/time and all random streams.
Compatible exploitation preserves state and forks future child randomness.
CPU uninterrupted/resumed training is tested for exact scientific-state equality.
CPU/CUDA trajectory equivalence is not asserted.

Each task writes an intent before work. A committed result replays without any
training. An unresolved intent is charged and refuses automatic redispatch.
Controller state is reconstructed deterministically from committed task results,
including proposals and lineage; complete replay is tested to leave the work
ledger unchanged. Checkpoints are trusted local Torch files, not untrusted input.

## Calling the companion

The operation runner installs the dependency paths and pinned environment.
Application code uses the following API within that environment:

```python
from hponas_rl_bgpbt.adapter import SACMember
from hponas_rl_bgpbt.transfer import distill

config = dict(actor_hiddens=[32, 16], critic_hiddens=[64, 32, 16],
              actor_lr=0.0007, critic_lr=0.0012)
member = SACMember(config, seed=42)
member.train(4096)
score = member.score()  # Complete finite-law cost and certified Riccati gap.
member.save("checkpoint.pt")
restored = SACMember.restore("checkpoint.pt")
child = restored.compatible_copy(dict(config, actor_lr=0.0003), seed=43)
new_shape = dict(config, actor_hiddens=[16, 16, 8])
student, transfer_receipt = distill(restored, new_shape, seed=44, steps=64)
```

Use `ResourceExecutor` with one CPU/thread and zero or one visible GPU per
worker. Submit `tasks.run_task` to carry task directories, source checkpoint
hashes and resource provenance. GPU visibility is installed before importing
Torch. Other processes may share a device. The hardware operation admits devices
with 4 GiB free, caps our Torch allocator at 1 GiB and monitors a 2 GiB owned
process-memory ceiling. Busy devices are not a correctness blocker and this
shared run does not estimate speedup. The exact stage commands and limits are in
`docs/PROGRAM_OPERATIONS.md`. A successful scientific operation cannot silently
allocate another run. A new study needs its own reviewed bounded manifest.

## Evidence and interpretation

The reviewed sequence is engineering, calibration, frozen search, fresh static
confirmation, hardware, documentation and independent audit. The static random
search baseline starts from the same four initial configurations and seeds. It
uses the same transitions and the same number of component-gradient minibatches:
120 extra SAC steps match 160 distillation steps over three components. This is
not equal FLOPs or equal wall time; both are distinct resource comparisons.

Confirmation seeds 801, 802 and 803 are reserved before search. Each method's
final selected architecture/rates are trained **from scratch**, so confirmation
tests the selected static configuration, not a replay of the evolved lineage.
The selected lineage and every proposal are retained separately. Three seeds
provide a small paired experiment; they cannot prove universal reliability or
global HPO/NAS optimality. The computed Riccati gap does certify each saved
deterministic policy's suboptimality on this declared finite task, up to reported
floating-point reconstruction tolerance.

The exact scorer canonicalizes identical float32 observations before inference.
This ensures duplicate histories choose one action rather than allowing batched
GEMM position rounding to correlate with unobserved future noise. The original
Riccati identity tolerance is unchanged. See the source-bound failed engineering
attempt and repaired position-sensitive test.

The extension is a bounded local companion for this continuous-control contract.
It is not a generic arbitrary-environment SAC service, distributed cluster
recovery, a global NAS certificate, or proof that BG-PBT beats random search.
Use the result and audit receipts for the actual measured outcome and current
CPU/GPU qualification status.
