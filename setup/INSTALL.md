# HPO Tuner Build Environment Setup

## Quick start

```bash
cd /home/ubuntu/workspace/hponas
conda env create -f setup/environment.yml
conda activate hponas
pytest tests/  # run when tests exist
```

## What gets installed

**Execution layer (wrapping)**
- `ray[tune]==2.58.0` — distributed execution, RLlib integration, checkpointing (current stable)
- `torch>=2.2.0` — executor dependency, also our NN workloads
- `gymnasium>=1.0.0` — RL environment interface
- `stable-baselines3>=2.4.0` — PPO reference for validation studies

**Searcher dependencies (tier 0: wrapping; tier 1+: building)**
- `botorch>=0.18.0` — qLogEI, qLogNEHVI, trust-region patterns (Ch4, Ch7)
- `gpytorch>=1.13` — GP models underneath BoTorch
- `optuna>=4.9.0` — TPE wrapper (Ch4 decision box)
- `ConfigSpace>=1.2.0` — mixed-space schema, DEHB dependency (Ch5)

**Infrastructure**
- `pandas`, `scikit-learn` — data layer, warm-start querying (Ch8)
- `pyyaml` — study declarations
- `tensorboard` — RLlib logging bridge
- `pytest` — validation suite runner (Ch14)

## Verification after install

```bash
python3 -c "import ray.tune; print(f'Ray Tune {ray.tune.__version__}')"
python3 -c "import botorch; print(f'BoTorch {botorch.__version__}')"
python3 -c "import optuna; print(f'Optuna {optuna.__version__}')"
python3 -c "from ray import train; from ray.tune.schedulers import ASHAScheduler; print('Ray APIs loadable')"
```

## Notes

Versions below were checked against PyPI on 2026-08-26; re-check before the build starts if that date has gone stale.

- Ray 2.58.0 is the current stable release. Pinned exactly (not `>=`) because the Tune scheduler and checkpoint APIs we build against have drifted across minor releases, and tier-2 population methods depend on checkpoint-surgery internals.
- BoTorch 0.18+ for qLogNEHVI and trust-region utilities (Ch7, Ch4). Floor is `>=` rather than pinned since BoTorch's public acquisition API has been stable.
- Optuna 4.9+ for the current TPE sampler (Ch4 evidence section).
- Python 3.12: Ray 2.58.0 publishes wheels for cp310–cp314, so 3.13 would also work. 3.12 is the conservative pick because our other dependencies (gpytorch, stable-baselines3) have had slower 3.13 uptake than Ray itself. Revisit at Phase 0 if any dependency forces the issue.

## What's NOT installed here (deferred or external)

- **Brax environments** — tier-1 gate dependency, install when V07/V08 campaigns start
- **DEHB** — tier-0 wrap target. Now available on PyPI (`dehb==0.1.2`), but the work breakdown assumes we verify the wrapped version against ConfigSpace compatibility before committing to the PyPI build vs a vendored copy from GitHub. Decision deferred to tier-0 start.
- **Ax** (Meta's BO library) — watchlist only, not a build dependency
- **Higher-cost backends** (Kubernetes Ray cluster) — production concern, not dev environment

## Troubleshooting

**Ray import fails**: Ray 2.58.0 requires Python >=3.10 and ships cp310–cp314 wheels, so a plain version mismatch is unlikely on 3.12. Check instead that the `[tune]` extra actually installed (`python3 -c "import ray.tune"` failing while `import ray` succeeds means the extra was dropped).

**BoTorch/GPyTorch version mismatch**: Uninstall both and reinstall BoTorch (pulls compatible GPyTorch).

**CUDA not found**: The env installs CPU-only PyTorch by default; for GPU builds, replace the torch line with the CUDA-enabled wheel per pytorch.org.
