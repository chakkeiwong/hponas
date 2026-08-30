# Handoff Summary: HPO Tuner Environment and Build Program

**Date:** 2026-08-26  
**Status:** Environment setup complete, build program ready for review  
**Next action:** Codex reviews [MEMO_TO_CODEX.md](MEMO_TO_CODEX.md), then Phase 0 starts

---

## What was delivered

1. **Environment setup** — [setup/environment.yml](setup/environment.yml) and [setup/INSTALL.md](setup/INSTALL.md)
   - 263 packages, 322 MB download, tested with `mamba env create --dry-run`
   - Ray 2.58.0 (current stable), BoTorch 0.18.1, Optuna 4.9.0, all verified against PyPI on 2026-08-26
   - Python 3.12 (Ray cp310–cp314 wheels available, 3.12 conservative for other deps)
   - Full pip resolution tested, no conflicts

2. **Build program** — [BUILD_PROGRAM.md](BUILD_PROGRAM.md)
   - Three-tier plan: 42 engineer-weeks implementation + 5 GPU-weeks validation
   - Three gates (weeks 6, 12, 30) with pass/fail criteria and demotion rules
   - Work breakdown to 0.5-day granularity for tier 0 and tier 1
   - Risk register with 6 tracked risks, tripwires, and mitigation

3. **Review memo** — [MEMO_TO_CODEX.md](MEMO_TO_CODEX.md)
   - Six review categories: feasibility, risks, hands-off executability, dependencies, validation staging, productionization boundary
   - Requested format: Green/Yellow/Red rating + callouts + one-sentence advice per category
   - Context: points to survey Chapters 11–15 (the product proposal)

4. **Starter repository structure**
   - `src/` with six modules (contracts, searchers, schedulers, store, executors, templates)
   - `tests/` with unit, integration, validation directories
   - `validation/tasks/` for pinned tasks, `validation/results/` for campaign data
   - [README.md](README.md) with project overview and build status tracker
   - [docs/progress.md](docs/progress.md) with weekly checklist structure
   - `.gitignore` for Python, Ray, Jupyter, validation results

5. **Survey artifact** — [hpo-survey/main.pdf](hpo-survey/main.pdf) (context, not a deliverable)
   - 106 pages, 0 LaTeX errors, ready for colleague review
   - Chapters 11–15 are the product proposal; the rest is method teaching
   - Referenced by the build program for decision-box verdicts and validation suite

---

## Verification checklist (all passed)

- [x] `mamba env create -f setup/environment.yml --dry-run` resolves (263 packages)
- [x] Pip dependency block resolves without conflicts (tested with `pip install --dry-run`)
- [x] Ray 2.58.0 version confirmed on PyPI (checked 2026-08-26)
- [x] BoTorch 0.18.1, Optuna 4.9.0, DEHB 0.1.2 versions confirmed on PyPI
- [x] Survey page count matches memo claim (106 pages per main.log)
- [x] Directory structure created, `.gitkeep` files placed
- [x] No stale version pins from memory (original draft had Ray 2.40.0, corrected to 2.58.0)

---

## How to use this handoff

### For the reviewer (codex)
1. Read [MEMO_TO_CODEX.md](MEMO_TO_CODEX.md) — it frames the six review categories and requests a specific response format
2. Read [BUILD_PROGRAM.md](BUILD_PROGRAM.md) — the program being reviewed
3. Optionally consult [setup/INSTALL.md](setup/INSTALL.md) and survey Chapters 11–15 for context
4. Provide Green/Yellow/Red ratings + callouts for each of the six categories
5. Your review gates whether Phase 0 (interface freeze) starts this week

### For the builder (post-review)
1. Address any Red or Yellow callouts from codex review
2. Install environment: `mamba env create -f setup/environment.yml && conda activate hponas`
3. Verify installation: run the four verification commands in [setup/INSTALL.md](setup/INSTALL.md)
4. Start Phase 0 per [BUILD_PROGRAM.md](BUILD_PROGRAM.md) (weeks 1–2: interface freeze)
5. Update [docs/progress.md](docs/progress.md) weekly as work completes

---

## Files ready for review

| Path | Purpose | Size | Status |
|------|---------|------|--------|
| `BUILD_PROGRAM.md` | Three-tier build plan | 18 KB | Ready |
| `MEMO_TO_CODEX.md` | Review request | 8 KB | Ready |
| `setup/environment.yml` | Conda environment spec | 0.5 KB | Tested |
| `setup/INSTALL.md` | Install notes + troubleshooting | 2 KB | Ready |
| `README.md` | Project overview | 4 KB | Ready |
| `docs/progress.md` | Weekly tracker template | 2 KB | Ready |
| `hpo-survey/main.pdf` | Survey (context) | 900 KB | Ready (106p) |

---

## Key decisions made during setup

1. **Python 3.12 over 3.13** — Ray supports both, but 3.12 is conservative for other deps
2. **Ray pinned exactly (==2.58.0)** — Tune scheduler API has drifted across minors; tier-2 population methods depend on checkpoint-surgery internals
3. **BoTorch floor (>=0.18.0), not pinned** — public acquisition API has been stable
4. **DEHB decision deferred** — PyPI version exists (0.1.2), but tier-0 breakdown assumes we verify ConfigSpace compatibility first before committing to PyPI vs GitHub vendor
5. **Conda + pip hybrid** — conda for numpy/scipy/matplotlib (binary compat), pip for the ML stack (faster updates)

---

## What's NOT in this handoff (by design)

- **No code yet** — Phase 0 writes the interfaces, tier 0 writes the first working code
- **No validation task sizing** — Phase 0 work item, requires profiling Brax/PPO/Hamiltonian on the target hardware
- **No store schema DDL** — Phase 0 deliverable after `StudySpec` contract is frozen
- **No pre-commitment to tier-2 scaling** — program says "1.5–2 engineers or extended timeline," decision deferred to week-12 gate

---

## Open questions for codex review

1. **Sizing realism:** Is "Trust-region BO: 7 days" (3d adapt + 1d integrate + 1d test + 2d V04 campaign) aggressive, padded, or reasonable?
2. **Tripwire timing:** Week-22 flag for a week-30 BG-PBT gate — 8 weeks of lead time enough, or pilot earlier?
3. **Gate staging:** Are we deferring any "should have caught this at tier 1" tests to the tier-2 gate?
4. **Hands-off ready:** Can someone execute tier 0 from the program without clarifying questions, or does it need more detail?
5. **Demotion clarity:** "qLogNEHVI failure → demote to tier-2 option, Hamiltonian defaults to scalarization" — clear enough to act on at week 12, or needs a fallback work plan written now?
6. **Productionization boundary:** Is tier-2 output (week 30) usable for internal colleagues, or does it need the optional post-tier-2 hardening to be a real tool?

---

## Timeline

- **Today (2026-08-26):** Environment and program delivered, awaiting codex review
- **This week:** Codex reviews, feedback addressed, stakeholder sign-off on interfaces
- **Next week (week 1):** Phase 0 starts (interface freeze)
- **Week 2:** Phase 0 complete, stakeholder review of contracts
- **Weeks 3–6:** Tier 0 build
- **Week 6:** First gate (V01–V03, V05, V14)
- **Week 12:** Second gate (tier-1 methods)
- **Week 30:** Third gate (full suite, ship decision)

---

For questions, see the [MEMO_TO_CODEX.md](MEMO_TO_CODEX.md) logistics section.
