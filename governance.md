# Governance System for HPO Tuner Build

**Purpose:** Prevent drift, enforce gate discipline, maintain plan coherence  
**Status:** Proposed structure for Phase R1 completion → Tier 0 start

---

## 1. Single authoritative plan

**Document:** `BUILD_PROGRAM_v2.md`  
**Status:** To be generated from corrected inputs  
**Versioning:** Semantic (v2.0 = major scope, v2.1 = minor adjustments)

### Sources (inputs)

These three artifacts are the **specification layer**:

1. **hpo-survey-decisions.json** — 63 decisions, tiers, validation mappings  
2. **WORK_BREAKDOWN_TIMELINE_DRAFT.md** — effort, phasing, gate criteria  
3. **hpo-survey/sections/16-validation.tex** — validation protocols (V01–V15)

### Derived artifact (output)

**BUILD_PROGRAM_v2.md** is **generated** from the above via:

```bash
python3 tools/generate_build_program.py \
  --decisions hpo-survey-decisions.json \
  --timeline WORK_BREAKDOWN_TIMELINE_DRAFT.md \
  --validation hpo-survey/sections/16-validation.tex \
  --output BUILD_PROGRAM_v2.md
```

The generator produces:
- Phase/tier breakdowns with effort and calendar
- Gate criteria with pass/fail/hold conditions
- Traceability: decision → task → test → deliverable
- Risk register from timeline + decisions
- Cost summary table

**Regenerate when:**
- A decision changes tier or validation mapping (amend decisions.json)
- Work breakdown changes (amend timeline, regenerate, diff, decide)
- Validation protocol corrected (amend survey, regenerate)

### Approval and locking

Once BUILD_PROGRAM_v2.md is generated:

1. **Review** — stakeholders read the full program (not just diffs from v1)
2. **Approval** — sign off in `BUILD_PROGRAM_v2_APPROVAL.md` with date + names
3. **Lock** — commit approved version, tag as `program-v2.0`
4. **Amendments** — changes produce v2.1, v2.2, etc. with explicit deltas

**No execution against competing plans.** If you're working from BUILD_PROGRAM.md (v1) and WORK_BREAKDOWN_TIMELINE_DRAFT.md at the same time, you have no contract.

---

## 2. Phase exit gates with mechanical verification

Every phase (R1, Tier 0, Tier 1, Tier 2, Distributed Beta) ends with a **gate check** that runs:

```bash
python3 tools/gate_check.py --phase r1
```

The script verifies:

### Deliverables exist
```python
# R1 example
required_files = [
    "examples/spike_branin.py",
    "examples/spike_crash_recovery.py",
    "hponas/architecture.py",
    "docs/SPIKE_REVIEW.md",           # MISSING in current state
    "tests/test_searchers.py",
]
for f in required_files:
    assert Path(f).exists(), f"Missing deliverable: {f}"
```

### Exit criteria pass
```python
# R1 example
result = subprocess.run(["python3", "examples/spike_branin.py"], 
                       capture_output=True, timeout=120)
assert result.returncode == 0, "spike_branin.py failed"
assert "DETERMINISM TEST PASSED" in result.stdout.decode()

# Check uniqueness on CONFIG, not trial_id (catches Sobol resume bug)
store = Store("spike_crash_recovery.db")
configs = [trial.config for trial in store.trials]
assert len(configs) == len(set(map(tuple, map(dict.items, configs)))), \
    "Crash recovery produced duplicate configs"
```

### Documentation synchronized
```python
# Check README claims match reality
readme = Path("README.md").read_text()
survey_pages = int(re.search(r"(\d+) pages", readme).group(1))
actual_pages = get_pdf_page_count("hpo-survey/main.pdf")
assert survey_pages == actual_pages, \
    f"README claims {survey_pages}p, actual {actual_pages}p"

# Check progress.md phase matches git tags
assert "R1 complete" in Path("docs/progress.md").read_text(), \
    "progress.md not updated for R1 completion"
```

### No blockers
```python
# Parse BUILD_PROGRAM_v2.md gate criteria for current phase
gate = parse_gate_criteria("BUILD_PROGRAM_v2.md", phase="r1")
for criterion in gate.exit_criteria:
    assert criterion.status == "met", \
        f"Blocker: {criterion.name} = {criterion.status}"
```

**Output:** `gate_reports/r1_gate_YYYY-MM-DD.md` with pass/fail/hold + findings

**Blocking rule:** Next phase cannot start until gate returns **pass**. A gate that returns **hold** means "not ready" (missing deliverables, open findings). A gate that returns **fail** means "criteria not met after completion" (tests fail, performance below threshold) and triggers demotion rules from the program.

---

## 3. Progress tracking generated from ground truth

**Problem:** `docs/progress.md` hand-updated → gets stale  
**Solution:** Generate progress from verifiable state

```bash
python3 tools/update_progress.py
```

Reads:
- Git tags (which phases are locked?)
- Test results (`pytest --json` → coverage, pass count)
- File existence (which deliverables exist?)
- Gate reports (what's the last gate verdict?)
- Commit history (when was each phase finished?)

Writes `docs/progress.md`:

```markdown
# Build Progress

**Last generated:** 2026-08-31 (automated)  
**Current phase:** R1 Spike  
**Status:** BLOCKED on gate (see findings below)  

## R0 Specification Correction
✅ Complete (2026-08-28)  
- All exit criteria met  
- Outstanding: Statistical reviewer verification (deferred, non-blocking)

## R1 Executable Spike
🔶 Implementation complete, gate BLOCKED (2 findings)  
**Completed:**
- [x] Study runs end-to-end (branin example: 8 trials, 0.01s)
- [x] Determinism test passes
- [x] 52 tests, 93% coverage
- [x] Architecture factory stubs enforce compatibility

**BLOCKERS:**
1. Searcher state not serializable → crash recovery produces duplicate configs
2. RayExecutor is stub (no real Ray) → conformance test is local-vs-local
3. docs/SPIKE_REVIEW.md missing → interfaces not formally approved

**Next:** Fix blockers, re-run gate check, obtain stakeholder sign-off

---
_Progress auto-generated from: git tags, test results, gate_reports/r1_gate_2026-08-31.md_  
_To update: `python3 tools/update_progress.py`_
```

**Rule:** Commit the generated progress.md, don't hand-edit it. If the script's output is wrong, fix the script or the ground truth, not the output.

---

## 4. Traceability enforcement

The decisions.json → tasks → tests → deliverables chain must stay connected.

### At phase start: task generation

```bash
python3 tools/generate_tasks.py --phase tier0 --output tier0_tasks.json
```

Reads `hpo-survey-decisions.json`, filters to tier=T0, generates:

```json
{
  "phase": "tier0",
  "tasks": [
    {
      "id": "T0-searcher-tpe",
      "decision_id": "ch03-04",
      "description": "TPE via Optuna wrapper",
      "effort_days": 4,
      "dependencies": ["T0-space-conditionals"],
      "deliverables": ["hponas/searchers/tpe.py", "tests/test_tpe.py"],
      "validation": ["V04-T0"]
    },
    ...
  ]
}
```

### During phase: task tracking

Track completion in `tier0_tasks.json`:

```json
{
  "id": "T0-searcher-tpe",
  "status": "complete",
  "completed_date": "2026-09-15",
  "actual_effort_days": 3.5,
  "deliverables_verified": true
}
```

### At gate: validation mapping check

Gate script verifies every decision marked tier=T0 has:
- Implementation task completed
- Deliverable files exist
- Validation entry run (if mapped)

```python
for decision in decisions_json["tier0"]:
    task = find_task(decision.id)
    assert task.status == "complete", f"Decision {decision.id} incomplete"
    
    if decision.validation_entries:
        for v in decision.validation_entries:
            result = validation_results[v]
            assert result in ["pass", "hold", "demote"], \
                f"{v} for {decision.id} not run"
```

**Breaks the build if:** A decision's task is done but its validation isn't run, or a validation references a decision that doesn't exist.

---

## 5. Change control: when plans diverge from execution

### Scenario A: Estimate was wrong

**Example:** Tier 0 GP+qLogEI takes 12 days, not 8.

**Process:**
1. Update `tier0_tasks.json` actual_effort
2. Run `python3 tools/timeline_impact.py` → shows cascade (Tier 0 gate slips 4 days)
3. Decide: absorb within contingency, or amend program?
4. If amending: regenerate BUILD_PROGRAM_v2.1.md, diff v2.0, get approval
5. Commit amendment with `AMENDMENT_v2.0_to_v2.1.md` explaining change

### Scenario B: Validation demotes a method

**Example:** V09 shows qLogNEHVI ties Chebyshev → demotion rule triggers.

**Process:**
1. Gate script detects demotion, writes finding in gate report
2. Demotion rule (from program): "demote to option, Hamiltonian defaults to scalarization"
3. Update `hpo-survey-decisions.json`: change verdict from "include-default" to "include-option"
4. Regenerate BUILD_PROGRAM to reflect reduced scope
5. Commit as planned demotion (not a failure)

### Scenario C: Survey correction needed

**Example:** Statistical reviewer finds V11 margin too tight, requests 15% not 10%.

**Process:**
1. Amend `hpo-survey/sections/16-validation.tex` with correction
2. Regenerate BUILD_PROGRAM (validation protocol changes)
3. Re-run affected validation (V11) with new protocol
4. Document as survey erratum, not program drift

---

## 6. Operational discipline

### Weekly check-in (during active phase)

Run these three commands:

```bash
# 1. Regenerate progress from ground truth
python3 tools/update_progress.py

# 2. Check for uncommitted plan changes
git diff BUILD_PROGRAM_v2.md hpo-survey-decisions.json

# 3. Verify current task tracking is live
python3 tools/task_status.py --phase tier0
```

If progress diverges from plan:
- Small (1-2 day slip): note in progress.md, continue
- Medium (>3 days or scope change): update tasks.json, run timeline impact
- Large (gate criteria unmet): hold, diagnose, amend or replan

### Gate discipline (phase boundaries)

Before calling a phase complete:

1. **Self-check:** Developer runs `gate_check.py --phase X --mode dry-run`
2. **Fix findings:** Address blockers until dry-run passes
3. **Formal gate:** Run `gate_check.py --phase X` and commit report
4. **Stakeholder review:** If program requires (R1, Tier 1 gate, Tier 2 gate)
5. **Lock phase:** Git tag `phase-X-complete`, update progress
6. **Start next:** Generate tasks for next phase, commit initial tasks.json

**Never skip a gate.** If you're in Tier 0 with R1 blockers still open, go back and close R1 properly.

---

## 7. Automation: CI enforcement

Add to `.github/workflows/governance.yml`:

```yaml
name: Governance checks

on: [push, pull_request]

jobs:
  plan-coherence:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # Verify BUILD_PROGRAM is in sync with inputs
      - name: Regenerate BUILD_PROGRAM
        run: python3 tools/generate_build_program.py --verify
        # Exits 1 if generated output differs from committed BUILD_PROGRAM_v2.md
      
      # Verify progress.md is current
      - name: Regenerate progress
        run: |
          python3 tools/update_progress.py
          git diff --exit-code docs/progress.md
      
      # If we're past a gate, verify gate report exists
      - name: Check gate reports
        run: python3 tools/verify_gates.py
  
  current-phase-tests:
    runs-on: ubuntu-latest
    steps:
      # Detect current phase from progress.md
      - name: Determine phase
        id: phase
        run: echo "current=$(python3 tools/current_phase.py)" >> $GITHUB_OUTPUT
      
      # Run phase-specific checks
      - name: Run phase gate check (non-blocking)
        run: python3 tools/gate_check.py --phase ${{ steps.phase.outputs.current }} --mode dry-run
        continue-on-error: true  # Don't block PR, but show findings
```

**Result:** PRs that drift BUILD_PROGRAM without regenerating it, or skip gate checks, fail CI.

---

## 8. Document hierarchy (what to read when)

**For execution (implementers):**
1. `BUILD_PROGRAM_v2.md` — the authoritative plan
2. `docs/progress.md` — current state (auto-generated)
3. `tier0_tasks.json` (or current phase) — your work breakdown

**For governance (leads):**
1. `gate_reports/` — phase exit verdicts
2. `AMENDMENT_*.md` — scope/timeline changes
3. Timeline impact reports from `tools/timeline_impact.py`

**For specification (reviewers):**
1. `hpo-survey-decisions.json` — what we're building and why
2. `hpo-survey/sections/16-validation.tex` — how we'll know it works
3. `WORK_BREAKDOWN_TIMELINE_DRAFT.md` — effort model (until consolidated into v2)

**Archive these once BUILD_PROGRAM_v2 is approved:**
- `BUILD_PROGRAM.md` → `archive/BUILD_PROGRAM_v1_REJECTED.md`
- `BUILD_PROGRAM_RECONCILIATION_COMPLETE.md` → fold into v2 generation
- `WORK_BREAKDOWN_TIMELINE_DRAFT.md` → source for v2, then archive

---

## 9. Immediate actions to establish governance

### This week (before Tier 0 starts):

1. **Close R1 properly** (3-5 days)
   - Fix searcher state serialization bug
   - Tighten crash recovery test (check config uniqueness)
   - Wire RayExecutor to real Ray, or restate exit criterion
   - Write `docs/SPIKE_REVIEW.md`
   - Run `gate_check.py --phase r1` (will need to write the script first)
   - Obtain stakeholder sign-off

2. **Write the governance tools** (2-3 days)
   - `tools/generate_build_program.py` — decisions.json + timeline → BUILD_PROGRAM_v2.md
   - `tools/gate_check.py` — mechanical exit criteria verification
   - `tools/update_progress.py` — ground-truth → progress.md
   - `tools/generate_tasks.py` — decisions.json[tier=TX] → tierX_tasks.json
   - Start simple: file existence + test pass/fail, elaborate later

3. **Generate and approve BUILD_PROGRAM_v2** (1 day)
   - Run generator with current inputs
   - Review output (you + stakeholders)
   - Sign off in BUILD_PROGRAM_v2_APPROVAL.md
   - Git tag `program-v2.0`, archive v1 docs

4. **Initialize Tier 0 tracking** (0.5 day)
   - Generate `tier0_tasks.json` from decisions
   - Commit initial task breakdown
   - Set up CI governance checks

**Total: ~7-10 days to establish governance before Tier 0 implementation starts.**

---

## 10. How this prevents the drift you experienced

| Drift type | How governance catches it |
|------------|--------------------------|
| **Multiple competing plans** | Single BUILD_PROGRAM_v2 generated from source; CI rejects commits that don't regenerate |
| **Stale progress docs** | progress.md auto-generated from git tags, test results, gate reports |
| **Exit criteria not checked** | `gate_check.py` mechanically verifies before phase close; blocking |
| **Bugs shipped as "done"** | Gate tests tightened (config uniqueness, not just trial_id), must pass |
| **Survey vs program drift** | Program regenerated from survey register; diffs visible |
| **Scope creep invisible** | Amendment process: v2.0 → v2.1 with explicit delta and re-approval |
| **Traceability broken** | Decision → task → test → deliverable checked at each gate |
| **Documentation lags reality** | README page count checked in CI; progress.md generated, not hand-edited |

---

## Success criteria for governance itself

After 3 months (~ end of Tier 0):

- [ ] Zero instances of "which document is authoritative?"
- [ ] Zero instances of stale progress claims (README/progress.md auto-updated)
- [ ] Zero instances of phase declared complete with blockers open (gate scripts enforced)
- [ ] Amendments produce explicit v2.x with delta, not silent rewrites
- [ ] Validation demotion decisions logged and traced back to protocol
- [ ] Time spent on governance: <10% of implementation time (lightweight enough to sustain)

If governance overhead exceeds 10%, simplify tools. If drift still occurs, tighten automation.

---

**Recommendation:** Treat governance setup as part of R1 close, not as overhead before Tier 0. The 7-10 days buys you 39-48 weeks of execution with a working compass.
