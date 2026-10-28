# RL-LQR-03: local learner device setup repair

The shared-device attempt 20261027T125231Z admitted GPUs at 26% and 95%
utilization, with more than 43 GiB free each. RLlib's GPU get_device route calls
Ray AIR get_devices, whose NVIDIA manager calls ray.get_gpu_ids. Outside a Ray
session this auto-initializes a cluster in each local worker. Hundreds of child
processes exceeded the 16 GiB owned RSS cap; the runner stopped them after
38 seconds. A post-exit inspection found no live recorded descendants. No work
ledger was created, so no decorated sampler/optimizer work began. Two task
intents remain recorded as startup reservations; never silently redispatch them.

The fixed local executor already assigns CUDA_VISIBLE_DEVICES before imports.
Use a narrowly scoped SACTorchLearner subclass that installs that explicit device
at the module-construction hook, before model parameters, alpha and optimizers
are created. Keep num_learners and Ray-managed GPUs at zero and retain all
upstream SAC training methods. No monkeypatch of Ray/PyTorch or loss functions.
Disable Ray autoconnection in the fixed runner so future accidental cluster calls
fail instead of creating a cluster. CPU construction and prior scientific runs
remain unchanged.

DEVICE-REPAIR runs the seven adapter tests and an additional construction
equivalence/no-Ray test. Ceiling: 1024 transitions, 256 SAC updates, 64
distillation updates, 300 seconds, three CPUs and 16 GiB owned RSS. Bind its
receipt before a new HARDWARE attempt using the same 2048/512/64 allocation.
The hardware attempt must prove actual CUDA updates, compatible and distilled
descendants, cross-GPU/CPU restoration and absence of Ray initialization.
Retain the failed startup receipt and verify cleanup. The final audit treats
expected stopped failures as failures with cleanup evidence, not as successful
operations. No scientific search is repeated and no memory ceiling is raised.
