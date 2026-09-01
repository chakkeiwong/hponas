# hponas — Hyperparameter Tuning for Workspace Projects

A workspace-internal hyperparameter tuning system serving RL (PPO on RLlib), Hamiltonian neural networks, neural-transport samplers, and multi-objective financial models.

**Status:** R1 spike complete, Tier 0 ready to start  
**Survey:** [hpo-survey/main.pdf](hpo-survey/main.pdf) (118 pages, ready for review)  
**Build program:** [BUILD_PROGRAM.md](BUILD_PROGRAM.md) (v2 pending generation)  
**Environment setup:** [setup/INSTALL.md](setup/INSTALL.md)

## Quick links

- **For reviewers:** Read the [survey Chapters 11–15](hpo-survey/main.pdf) (the product proposal) and the [memo to codex](MEMO_TO_CODEX.md)
- **For builders:** Start with [BUILD_PROGRAM.md](BUILD_PROGRAM.md) Phase 0, then follow the tier breakdowns
- **For users (post-build):** See `examples/quickstart.py` (will exist after tier 0)

## Repository structure

```
hponas/
├── src/                     # Main package
│   ├── contracts/           # Study spec, search space, protocols
│   ├── searchers/           # Search algorithms (Sobol, TPE, DEHB, TuRBO, ...)
│   ├── schedulers/          # Early stopping, population (ASHA, MO-ASHA, PBT, ...)
│   ├── store/               # Run database (trials, lineage, diagnostics)
│   ├── executors/           # Adapters (RLlib, generic train loop)
│   └── templates/           # Workload templates (rl_routine, hamiltonian_mo, ...)
├── tests/
│   ├── unit/                # Fast isolated tests
│   ├── integration/         # End-to-end studies
│   └── validation/          # V01–V15 suite (expensive, gates)
├── validation/
│   └── tasks/               # Pinned validation tasks with budgets
├── examples/                # Usage examples
├── docs/                    # Build progress, design notes
├── setup/                   # Environment and install
├── hpo-survey/              # The 106-page survey and product proposal
├── BUILD_PROGRAM.md         # Phased build plan with gates
└── MEMO_TO_CODEX.md         # Review request for build program
```

## Development status

**Phase 0 (weeks 1–2): Not started**  
Interface freeze, pinned task sizing, empty harness.

**Tier 0 (weeks 3–6): Not started**  
Wrap Sobol/TPE/DEHB, ASHA/Median, run store, RLlib adapter.  
**Gate:** V01–V03, V05, V14 pass.

**Tier 1 (weeks 7–12): Blocked on tier-0 gate**  
Build TuRBO, qLogEI+priors, qLogNEHVI, MO-ASHA, PriorBand, warm-start.  
**Gate:** V04, V09, V11 pass.

**Tier 2 (weeks 13–30): Blocked on tier-1 gate**  
Build PB2-Mix, BG-PBT, ifBO curve model, full validation suite.  
**Gate:** V07, V08, V15 pass.

## How to start building

1. **Review the program:** Read [BUILD_PROGRAM.md](BUILD_PROGRAM.md) and [MEMO_TO_CODEX.md](MEMO_TO_CODEX.md), provide feedback on feasibility/risks/scope.
2. **Set up environment:** `conda env create -f setup/environment.yml && conda activate hponas`
3. **Phase 0 (weeks 1–2):** Implement `src/contracts/` (study spec, search space schema, protocols), design store schema, write empty harness.
4. **Checkpoint:** Interface freeze reviewed by stakeholders before tier 0 starts.
5. **Tier 0 build:** Follow [BUILD_PROGRAM.md](BUILD_PROGRAM.md) tier-0 breakdown (6 weeks, 30 eng-days).
6. **Week 6 gate:** Run V01–V03, V05, V14 campaigns, apply demotion rules if any fail.
7. **Continue or pivot:** Gate pass → tier 1; gate fail → diagnose and replan.

## What this is (and isn't)

**IS:**
- A workspace-internal tuning system for four known workload families
- Built on Ray Tune (execution) + custom searchers/schedulers
- Opinionated (only includes methods that survived evidence review)
- Falsifiable (every method has a demotion rule tied to a validation test)

**IS NOT:**
- A general-purpose HPO library (not published to PyPI)
- A platform (no multi-tenancy, no web UI)
- A research contribution (wraps and integrates published methods)
- A zero-touch AutoML (requires workload-specific template selection)

## Key design decisions (from survey)

1. **Ray Tune as execution layer:** Yes (Ch10 audit: active maintenance, RLlib integration, checkpoint primitives for population methods)
2. **Routine-budget default:** ASHA + (TPE or DEHB) — low-cost, evidence-backed floor (Ch3–5)
3. **Differentiators:** qLogNEHVI for MO (Ch7), priors (Ch8), BG-PBT for large-parallel RL (Ch6)
4. **Not included:** BOHB (Optuna wraps it), raw EI (dominated by qLogEI), weighted-sum MO (can't reach concave Pareto fronts)
5. **Validation gates enforce verdicts:** 15 tests (V01–V15), three tiers, demotion rules written before code (Ch14)

## Questions or issues

- **Survey questions:** See [hpo-survey/literature-audit.md](hpo-survey/literature-audit.md) for sourcing log
- **Build program questions:** Raise in [MEMO_TO_CODEX.md](MEMO_TO_CODEX.md) review or file an issue
- **Environment issues:** See [setup/INSTALL.md](setup/INSTALL.md) troubleshooting section

## License and usage

Workspace-internal. Not licensed for external distribution.
