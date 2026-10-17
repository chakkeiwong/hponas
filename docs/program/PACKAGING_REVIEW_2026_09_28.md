# Installation and maintained-example review — PKG-01

Date: 2026-09-28, Asia/Shanghai. **PKG-01 installation deliverable verified; no scientific acceptance or release certification.**

## Verified support envelope

| Configuration | Dependency resolution and execution |
|---|---|
| Linux x86_64 CPU, CPython 3.12.14 | Fresh venv without system packages; core and `tpe,cmaes,ray,validation,test` extras resolved; dependency check clean; installed GP/Store recovery, progressive PASHA, CMA-ES, TPE and local Ray passed. |
| Linux x86_64 CPU, CPython 3.13.13 | Same checks passed. Pinned `rl` extra also resolved; real PPO training, policy checkpoint reload and separate protected evaluation passed. |
| Maintained Branin/recovery examples | Python 3.12 and 3.13, executed by absolute script path outside the checkout against the installed wheel. Full local/Ray proposal, fidelity and objective traces agree. Recovery preserves committed results and agrees exactly with an uninterrupted Sobol run. |
| Maintained PPO examples | Both normal and compatibility entry points passed on Python 3.13 with the installed RL extra. Training and protected evaluation remain separate. |
| Audited validation CLI | Deliberately source-checkout-only: requires full Git checkout, tests, examples, dependencies and protocols for the existing fingerprint. Wheel API raises `AuditContextError`; CLI exits 2 with instructions, before creating campaign artifacts. |

No Windows, macOS, ARM, GPU, multi-node, Python 3.14+, or Python 3.12 RL verification is claimed. `requires-python >=3.12` is a resolver constraint, not proof for every future interpreter. Linux results on this host do not establish universal platform support. Optional priors, deferred MO prototypes and distributed production are outside this verified installation envelope.

Resolved versions include NumPy 2.5.3, SciPy 1.18.1, torch 2.14.0+cpu, GPyTorch 1.15.2, BoTorch 0.18.1, Optuna 4.9.0, cmaes 0.12.0 and Ray 2.58.0. The Python 3.13 RL environment has JAX/jaxlib 0.11.2 and Brax from Git revision `57d5b863fcc66a29a2e043182c07a14a3dee3a7c`; its package version reports 0.14.2, which does not identify the PyPI build. Exact dependency freezes and installation logs are retained.

## Reproduced defects and repairs

1. Installed audit metadata previously raised `FileNotFoundError` for site-packages/pyproject.toml, after the runner could create an output directory. Audit provenance now fails explicitly before writes. The fingerprint algorithm and evidence thresholds are unchanged; a wheel hash never substitutes for repository identity.
2. Branin and recovery examples called removed executor/searcher APIs. They now use public Study, Store and checkpoint interfaces. Recovery no longer deletes `/tmp/hponas_crash`; neither does the older spike gate. Each run retains a fresh directory.
3. The old PPO example passed protected seed 999 to training and falsely claimed broad completion. Both maintained entry points now use the real bounded workflow and clearly label the result as integration evidence, with separate checkpoint evaluation.
4. Two later-tier prototypes call unsupported MO/Store/knob APIs. They remain visibly deferred under T1-MO/WL-01 in [the complete example inventory](../../examples/README.md); they are not counted as passing examples.

Original examples are archived with hashes. The 21 focused regression tests cover provenance refusal before side effects, incomplete/unrelated checkout rejection, full local trace determinism, committed-prefix preservation and honest example result labeling. CI now contains an isolated-wheel/core-example check; that CI configuration has not been run remotely in this session.

## Evidence and limits

[Verification receipt](evidence/2026-09-28/pkg-01/verification.json) binds the actual logs and exact source fingerprint. The first isolated dependency resolution completed in 1,813.30 seconds within its 2,400-second wall cap. Download transfer bytes were not instrumented; the retained cache occupies 3,456,425,844 bytes, which is not a network-transfer measurement. All work used two CPU-affinity slots and no GPU allocation.

After source repairs, the package was rebuilt offline and reinstalled with `--no-deps` into those environments. This second pass reuses the clean resolved dependencies; it is not represented as another independent dependency resolution. All 89 wheel Python files matched the checkout at build time. The first repair-build attempt failed because the execution PATH lacked Python >=3.12; its failure is preserved, and the successful attempt selected the already installed Python 3.13 explicitly. Original failure reproductions and both build attempts remain available.

Subsequent source edits require affected installation checks again. PKG-01 completion does not refresh V01/V02/V03/V14 or resolve D-PROTOCOL, D-TIERS, ASHA/median conformance, or full PPO acceptance. The next eligible action is **PRI-01**, already in the master program, while those dependent campaigns remain blocked.
