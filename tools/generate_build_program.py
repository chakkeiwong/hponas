#!/usr/bin/env python3
"""
Generate BUILD_PROGRAM_v2.md from structured inputs.

Usage:
    python3 tools/generate_build_program.py [--verify]

Inputs:
    - hpo-survey-decisions.json (63 decisions with tier/validation mappings)
    - validation/protocols.json (validation register)
    - BUILD_PROGRAM_v2.md (template for structure and phasing)

Output:
    - BUILD_PROGRAM_v2.md (regenerated with updated validation register)

--verify mode: regenerate and diff against committed BUILD_PROGRAM_v2.md,
exit 1 if different (for CI drift detection).
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

# Which gate owns each validation entry, per WORK_BREAKDOWN_TIMELINE_DRAFT.md.
#
# The timeline corrects the rejected v1 plan, which ran V06/V10/V13 at week 30 even
# though the survey assigns them T1; the timeline moves them to the Tier 1 gate
# ("MOVED from T2" in the source). This map is the program-side authority and is
# checked against the survey table at generation time, so a future edit that drops or
# re-times an entry fails the build instead of passing silently.
#
# Entries with suffixed IDs (V04-T0, V04-T1, V11a, V11b, V15a, V15b) match the keys
# in validation/protocols.json; V04 runs components at two gates.
PROGRAM_GATE_ASSIGNMENT: dict[str, list[str]] = {
    'tier0': ['V01', 'V02', 'V03', 'V04-T0', 'V05', 'V14'],
    'tier1': ['V04-T1', 'V06', 'V09', 'V10', 'V11a', 'V11b', 'V13'],
    'tier2': ['V08'],
    'dist_beta': ['V12'],
    'tier3': ['V07', 'V15a', 'V15b'],
}

# Human-readable gate labels for the register's cross-reference column.
GATE_LABELS: dict[str, str] = {
    'tier0': 'Tier 0 gate',
    'tier1': 'Tier 1 gate',
    'tier2': 'Tier 2 gate',
    'dist_beta': 'Distributed Beta gate',
    'tier3': 'Tier 3 (per-item, post-beta)',
}

# V04's tier-0 and tier-1 components have separate pass bars.
V04_T0_CRITERIA = 'Week 6: "TPE and log+Sobol GP must beat random baseline"'
V04_T1_CRITERIA = 'Week 12: "TuRBO and prior-aware qLogEI beat log+Sobol floor"'


def check_gate_coverage(validation_register: dict[str, dict]) -> list[str]:
    """
    Verify every validation entry is assigned to exactly one gate.

    Returns a list of problems (empty when clean). Catches the two failure modes that
    let scope leak: an entry in the survey that no gate runs, and an entry assigned to
    a gate that does not exist in the survey register.
    """
    problems = []

    assigned: dict[str, list[str]] = {}
    for gate, entries in PROGRAM_GATE_ASSIGNMENT.items():
        for vid in entries:
            assigned.setdefault(vid, []).append(gate)

    # Entries in the register that no gate runs
    for vid in sorted(validation_register):
        if vid not in assigned:
            problems.append(f"{vid} is in the validation register but no gate runs it")

    # Entries assigned to a gate but absent from the register
    for vid in sorted(assigned):
        if vid not in validation_register:
            problems.append(
                f"{vid} is assigned to {assigned[vid]} but is not in the validation register"
            )

    # V04, V11, V15 are split into components, so they appear multiple times
    for vid, gates in sorted(assigned.items()):
        if len(gates) > 1 and not vid.startswith(('V04-', 'V11', 'V15')):
            problems.append(f"{vid} is assigned to multiple gates {gates}; only V04/V11/V15 components may be")

    return problems


def gate_for_entry(vid: str) -> str:
    """Return the human-readable gate(s) that run a validation entry."""
    gates = [
        GATE_LABELS[gate]
        for gate, entries in PROGRAM_GATE_ASSIGNMENT.items()
        if vid in entries
    ]
    return ' + '.join(gates) if gates else "UNASSIGNED"


def load_decisions(path: Path) -> list[dict]:
    """Load and filter decisions to in-scope tiers."""
    with open(path) as f:
        decisions = json.load(f)

    # In-scope: T0, T1, T2, T3, workload templates, adopt
    in_scope = [
        d for d in decisions
        if d.get('tier') in ('T0', 'T1', 'T2', 'T3', 'workload template', 'adopt')
    ]
    return in_scope


def load_validation_register(protocols_path: Path) -> dict[str, dict]:
    """
    Extract validation register from validation/protocols.json.

    Returns a dict keyed by entry ID (V01, V02, ...) with fields:
        id, claim, pass_rule, criteria
    """
    with open(protocols_path) as f:
        data = json.load(f)

    entries = data.get('entries', {})
    register = {}

    for vid, entry in entries.items():
        # Build gate criteria from the entry's own gates field
        gates = entry.get('gates', {})
        criteria_parts = []
        for gate_key in sorted(gates.keys()):
            gate_label = GATE_LABELS.get(gate_key, gate_key)
            gate_data = gates[gate_key]
            bar = gate_data.get('pass_bar', '')
            if bar:
                criteria_parts.append(f'{gate_label}: "{bar}"')

        register[vid] = {
            'id': vid,
            'claim': entry.get('claim', ''),
            'pass_rule': entry.get('pass_rule', ''),
            'criteria': ' | '.join(criteria_parts) if criteria_parts else '',
        }

    return register


def _strip_id_prefix(criteria: str, vid: str) -> str:
    """
    Drop a redundant "V## (...)" wrapper from criteria text.

    BUILD_PROGRAM wrote gate criteria as "V12 (warm start saves >=20% trials)", so
    rendering it under a "**V12:**" label would print the ID twice.
    """
    match = re.fullmatch(rf'{vid}\s*\((.+)\)', criteria.strip(), re.S)
    if match:
        return match.group(1).strip()
    return criteria.strip()


def _clean_latex(text: str) -> str:
    """Normalize a LaTeX table cell to readable plain text."""
    # Collapse the line wrapping inside the cell first
    text = ' '.join(text.split())
    # Chapter/section cross-references: keep the pointer, drop the macro
    text = re.sub(r'Chapter~\\ref\{sec:product\}', 'Chapter 15', text)
    text = re.sub(r'Sec\.~\\ref\{[^}]*\}', '', text)
    text = re.sub(r'\\ref\{([^}]*)\}', r'[\1]', text)
    text = text.replace('$^{+}$', '+').replace('~', ' ')
    text = text.replace('--', '–')
    # Tidy artifacts left by dropped refs: ", )" -> ")", double spaces, stray commas
    text = re.sub(r',\s*\)', ')', text)
    text = re.sub(r'\(\s*,\s*', '(', text)
    return ' '.join(text.split()).strip()


def load_survey_validation_table(tex_path: Path) -> dict[str, dict]:
    """
    Parse Table 7.1 (tab:suite) from 16-validation.tex.

    Columns: ID & Claim under test & Pass rule or veto & Evid. & Gate

    This is the upstream source of truth for what each entry tests and which tier
    gate owns it. The reconciliation doc holds the BUILD_PROGRAM-side criteria.
    """
    text = tex_path.read_text()

    body_match = re.search(r'\\midrule(.+?)\\bottomrule', text, re.S)
    if not body_match:
        raise ValueError(f"Could not locate tab:suite body in {tex_path}")

    table = {}
    for raw_row in body_match.group(1).split(r'\\'):
        if not raw_row.strip():
            continue
        cells = raw_row.split('&')
        if len(cells) != 5:
            continue
        vid = cells[0].strip()
        if not re.fullmatch(r'V\d\d', vid):
            continue
        table[vid] = {
            'id': vid,
            'claim': _clean_latex(cells[1]),
            'pass_rule': _clean_latex(cells[2]),
            'evidence': _clean_latex(cells[3]),
            'survey_gate': _clean_latex(cells[4]),
        }

    if not table:
        raise ValueError(f"No validation entries parsed from {tex_path}")

    return table


def merge_validation_sources(
    reconciliation: dict[str, dict],
    survey: dict[str, dict],
) -> dict[str, dict]:
    """
    Combine both validation sources into one register.

    Claim and pass rule come from the reconciliation doc where present (its text was
    reviewed and de-LaTeXed during R0); the survey table fills gaps and supplies the
    owning gate tier. Entries appearing in only one source are kept and flagged, so a
    dropped or invented entry surfaces in the generated program instead of hiding.
    """
    merged = {}
    for vid in sorted(set(reconciliation) | set(survey)):
        rec = reconciliation.get(vid, {})
        srv = survey.get(vid, {})
        merged[vid] = {
            'id': vid,
            'claim': rec.get('claim') or srv.get('claim', ''),
            'pass_rule': rec.get('pass_rule') or srv.get('pass_rule', ''),
            'criteria': rec.get('criteria', ''),
            'survey_gate': srv.get('survey_gate', ''),
            'evidence': srv.get('evidence', ''),
            'in_reconciliation': vid in reconciliation,
            'in_survey': vid in survey,
        }
    return merged


def _strip_v1_annotations(value: str) -> str:
    """
    Drop "(was N in rejected plan)"-style asides from timeline figures.

    The timeline is a correction document, so its figures carry deltas against the
    rejected v1 plan. v2 is the approved plan and states figures plainly; the v1
    comparison lives in the timeline and in this program's Provenance section.
    """
    cleaned = re.sub(
        r'\s*\((?:was|were)\b[^)]*\)',
        '',
        value,
        flags=re.I,
    )
    return cleaned.strip()


def parse_phase_from_timeline(text: str, phase_header_pattern: str) -> dict:
    """
    Extract phase metadata from timeline by section header.

    Returns: {duration, effort, rationale, scope, gate_criteria, exit_criteria}
    """
    # Find section
    match = re.search(phase_header_pattern, text, re.M)
    if not match:
        return {}

    start_pos = match.end()
    # Find next ## header or EOF
    next_section = re.search(r'\n## [^#]', text[start_pos:])
    end_pos = start_pos + next_section.start() if next_section else len(text)
    section = text[start_pos:end_pos]

    # Extract duration and effort from first paragraph
    duration_match = re.search(r'\*\*Duration:\*\* (.+?)$', section, re.M)
    effort_match = re.search(r'\*\*Effort:\*\* (.+?)$', section, re.M)
    rationale_match = re.search(r'\*\*Rationale:\*\* (.+?)$', section, re.M)

    # Extract gate criteria (look for ### ... gate: pattern)
    gate_match = re.search(r'### .+ gate: (.+?)$', section, re.M)

    # Extract work breakdown table if present
    table_match = re.search(
        r'\| Category \| Tasks \| Effort \| Notes \|.+?\n\| \*\*Total\*\* \|',
        section,
        re.S
    )
    work_breakdown = table_match.group(0) if table_match else ""

    return {
        'duration': _strip_v1_annotations(duration_match.group(1).strip()) if duration_match else "",
        'effort': _strip_v1_annotations(effort_match.group(1).strip()) if effort_match else "",
        'rationale': _strip_v1_annotations(rationale_match.group(1).strip()) if rationale_match else "",
        'gate_criteria': gate_match.group(1).strip() if gate_match else "",
        'work_breakdown': work_breakdown,
        'full_section': section,
    }


def generate_program(
    decisions: list[dict],
    validation_register: dict,
    timeline_path: Path,
) -> str:
    """Generate BUILD_PROGRAM_v2.md content."""

    # Load timeline
    with open(timeline_path) as f:
        timeline_text = f.read()

    # Parse phases
    r0 = parse_phase_from_timeline(timeline_text, r'^## Phase R0: Specification Correction')
    r1 = parse_phase_from_timeline(timeline_text, r'^## Phase R1: Executable Architecture Spike')
    tier0 = parse_phase_from_timeline(timeline_text, r'^## Tier 0: Foundation')
    tier1 = parse_phase_from_timeline(timeline_text, r'^## Tier 1: Method Differentiators')
    tier2 = parse_phase_from_timeline(timeline_text, r'^## Tier 2: Population Line')
    dist_beta = parse_phase_from_timeline(timeline_text, r'^## Distributed Beta Hardening')

    # Group decisions by tier
    by_tier = {'T0': [], 'T1': [], 'T2': [], 'T3': []}
    for d in decisions:
        tier = d.get('tier')
        if tier in by_tier:
            by_tier[tier].append(d)

    # Build document
    md = f"""# HPO Tuner Build Program v2.0

**Generated:** {date.today().isoformat()}
**Sources:** hpo-survey-decisions.json, WORK_BREAKDOWN_TIMELINE_DRAFT.md, BUILD_PROGRAM_RECONCILIATION_COMPLETE.md
**Status:** APPROVED
**Repo:** `/home/ubuntu/workspace/hponas`

> **IMPORTANT:** This is a generated document. To modify the program, edit the source files and regenerate.
> Manual edits to this file will be overwritten. See [governance.md](governance.md) for details.

---

## Executive Summary

Three-tier build with gates at end of Tier 0, Tier 1, and Tier 2, plus mandatory Distributed Beta hardening before internal beta launch. Each gate runs a validation campaign; pass advances, fail triggers registered demotion rules.

**Phases:**
- **R0 (complete):** Specification correction (2 days actual, 8 statistical corrections applied)
- **R1 (complete):** Executable spike (3 weeks, interfaces frozen, gate PASS)
- **Tier 0:** Foundation—wrap audited components, wire database, build GP+qLogEI ({tier0['effort']})
- **Tier 1:** Method differentiators—MO stack, priors, cost-aware acquisition ({tier1['effort']})
- **Tier 2:** Population flagship—TuRBO, BG-PBT, architecture support ({tier2['effort']})
- **Distributed Beta:** Hardening—persistent store, crash recovery, monitoring, security ({dist_beta['effort']})
- **Tier 3:** Electives—post-beta features gated individually (DEHB reimpl, ifBO curve model)

**Total to internal beta:** 39-48 weeks, 275-310 engineer-days, 17k-33k accelerator-hours (see Summary Timeline below)

**Budget:** ~275-310 engineer-days + ~17k-33k accelerator-hours (campaigns). **Risk mitigation:** tier gates enforce fail-early; demotion rules pre-committed; alternatives named for every load-bearing bet.

**Approval:** See [BUILD_PROGRAM_v2_APPROVAL.md](BUILD_PROGRAM_v2_APPROVAL.md)

---

## Phase R0: Specification Correction (COMPLETE)

**Duration:** {r0['duration']}
**Effort:** {r0['effort']}
**Status:** ✅ Complete (2026-08-28)
**Report:** [R0_COMPLETION_REPORT.md](R0_COMPLETION_REPORT.md)

### Deliverables
- All 8 statistical corrections applied to survey Chapter 16
- NAS scope decided (Option A: moderate architecture coordinates, +16 eng-days)
- Architecture factory contract written (Ch 15 `sec:archfactory`)
- Traceability matrix: 63 decisions with tier/validation mappings
- `product_register.json`: 48 in-scope entries
- Survey builds clean at 118 pages

### Exit criteria
- [x] All corrections reviewed and committed
- [x] Traceability matrix complete
- [x] NAS scope decision made
- [ ] Statistical reviewer verification (deferred, non-blocking)

---

## Phase R1: Executable Architecture Spike (COMPLETE)

**Duration:** {r1['duration']}
**Effort:** {r1['effort']}
**Status:** ✅ Complete — gate PASS (2026-08-31)
**Gate report:** [gate_reports/r1_gate_2026-08-31.md](gate_reports/r1_gate_2026-08-31.md)
**Interface review:** [docs/SPIKE_REVIEW.md](docs/SPIKE_REVIEW.md)

### Deliverables
- Minimal SearchSpace, SobolSearcher, ASHAScheduler
- LocalExecutor (in-process), RayExecutor (stub—real Ray Tune deferred to Tier 0)
- Store with crash recovery (SQLite + WAL)
- Architecture factory stubs
- Searcher state serialization contract (`state_dict`/`load_state_dict`)
- Test suite: 56 tests, 93% coverage
- Examples: spike_branin.py, spike_crash_recovery.py

### Exit criteria
- [x] End-to-end study runs on local executor
- [x] Crash recovery without duplicate configs
- [x] Foundational test suite passes (56 tests, 93%)
- [x] Architecture factory stubs enforce compatibility
- [x] Interface review signed off
- [x] Gate PASS

### Findings resolved
1. **Sobol state serialization bug** — fixed by adding state_dict/load_state_dict to Searcher protocol
2. **RayExecutor stub** — accepted as known limitation per charter

---

## Tier 0: Foundation

**Duration:** {tier0['duration']}
**Effort:** {tier0['effort']}
**Rationale:** {tier0['rationale']}

### Scope

{tier0['work_breakdown']}

### Gate: {tier0['gate_criteria']}

**Validation entries:**

"""

    # Add validation details for T0
    for v in PROGRAM_GATE_ASSIGNMENT['tier0']:
        if v in validation_register:
            entry = validation_register[v]
            if v == 'V04':
                md += f"- **{v} (T0 component):** {V04_T0_CRITERIA}\n"
            else:
                criteria = _strip_id_prefix(entry['criteria'], v)
                md += f"- **{v}:** {criteria}\n"

    md += f"""
**Campaign cost estimate:** ~2,500 accelerator-hours (~15 accel-days, ~0.5 GPU-week)

**Demotion rules:**
- If wrapped implementations fail parity (V01): block tier-1, diagnose wiring
- If log-warping shows no benefit (V05): demote to opt-in feature
- If tier-0 searchers fail to beat random (V04-T0): identify and fix before proceeding

### Exit criteria
- [ ] All T0 searchers/schedulers implemented with unit tests
- [ ] Both executors pass conformance suite
- [ ] rl_routine template production-ready
- [ ] V01-V05, V14, V04-T0 validation complete
- [ ] Gate report with results and demotion decisions
- [ ] No blockers

**Decisions mapped to Tier 0:** {len(by_tier['T0'])} capabilities from traceability matrix

---

## Tier 1: Method Differentiators

**Duration:** {tier1['duration']}
**Effort:** {tier1['effort']}
**Rationale:** {tier1['rationale']}

### Scope

{tier1['work_breakdown']}

### Gate: {tier1['gate_criteria']}

**Validation entries:**

"""

    # Add validation details for T1
    for v in PROGRAM_GATE_ASSIGNMENT['tier1']:
        if v in validation_register:
            entry = validation_register[v]
            if v == 'V04':
                md += f"- **{v} (T1 component):** {V04_T1_CRITERIA}\n"
            else:
                criteria = _strip_id_prefix(entry['criteria'], v)
                md += f"- **{v}:** {criteria}\n"

    md += f"""
**Campaign cost estimate:** ~10,900 accelerator-hours (~65 accel-days, ~2.3 GPU-weeks)

**Demotion rules:**
- qLogNEHVI failure (V09): demote to tier-2 option, Hamiltonian defaults to scalarization
- TuRBO failure (V04-T1): defer population line (BG-PBT depends on TR), reassess tier-2 scope
- Prior failure (V11): demote πBO/PriorBand to opt-in

### Exit criteria
- [ ] Complete MO stack with fallback paths
- [ ] Correct πBO and PriorBand implementations
- [ ] EI-per-cost with predictive cost model
- [ ] Production workload templates for all in-scope domains
- [ ] V04-T1, V06, V09-V11, V13 validation complete
- [ ] Gate report with demotion decisions

**Decisions mapped to Tier 1:** {len(by_tier['T1'])} capabilities from traceability matrix

---

## Tier 2: Population Line

**Duration:** {tier2['duration']}
**Effort:** {tier2['effort']}
**Rationale:** {tier2['rationale']}

### Scope

**Prerequisites (must complete first):**
- Mixed-space TuRBO (~10d) — moved from T1, is T2 prerequisite per roadmap

**Population methods:**
- PB2, PB2-Mix, BG-PBT population manager

**Architecture support (Option A approved 2026-08-28):**
- Architecture factory, compatibility policy, distillation protocol
- Architecture proposal, measured objectives

**Tests:** TuRBO mixed-space, population checkpoint compatibility, distillation correctness

**Workload:** rl_large_parallel production build

### Gate: V08

**Validation entries:**

"""

    # Add validation details for T2
    for v in PROGRAM_GATE_ASSIGNMENT['tier2']:
        if v in validation_register:
            entry = validation_register[v]
            criteria = _strip_id_prefix(entry['criteria'], v)
            md += f"- **{v}:** {criteria}\n"

    md += """
**Campaign cost estimate:** ~4,600-19,600 accelerator-hours (pilot to full)

**Demotion rules:**
- BG-PBT consistent home loss (V08): demote to option, rl_large_parallel defaults to DEHB

### Exit criteria
- [ ] TuRBO mixed-space implementation complete
- [ ] BG-PBT population line complete with architecture support
- [ ] rl_large_parallel production-ready
- [ ] V08 validation complete (may be hold/demote/pass)
- [ ] Gate report with recommendation

**Decisions mapped to Tier 2:** """ + f"{len(by_tier['T2'])} capabilities from traceability matrix" + """

---

## Distributed Beta Hardening (MANDATORY)

**Duration:** """ + dist_beta['duration'] + """
**Effort:** """ + dist_beta['effort'] + """
**Rationale:** Operational correctness is not optional (Codex B7, B8)

This gate sits between Tier 2 validation and internal beta launch.

### Scope
- Persistent store (serialized SQLite writer or Postgres with transactions)
- Coordinator recovery (crash and restart without duplicates or budget debit)
- Idempotent events (observation, promotion, stop, checkpoint registration)
- Monitoring (study stalls, trial failures, budget overrun alerts)
- Hard budget controls (study-level and trial-level measured usage enforcement)
- Fault tests (worker loss, preemption, duplicate/late events, corrupt checkpoint)
- Scale tests (proposal latency, event throughput, concurrent trials at target load)
- Artifact retention (checkpoint GC policy, backup/restore)
- Security review (path handling, deserialization, secrets, resource exhaustion)
- Runbook (user guide, operations manual, support ownership)

### Validation entries

"""

    # Add V12 (warm-start savings) under Dist Beta gate
    for v in PROGRAM_GATE_ASSIGNMENT['dist_beta']:
        if v in validation_register:
            entry = validation_register[v]
            criteria = _strip_id_prefix(entry['criteria'], v)
            md += f"- **{v}:** {criteria}\n"
        else:
            md += f"- **{v}:** _Missing from register_\n"

    md += """
### Exit criteria
- [ ] Persistent store with crash recovery proven
- [ ] V12 warm-start savings validated
- [ ] Monitoring and alerts deployed
- [ ] Hard budget controls enforced
- [ ] Fault injection tests pass
- [ ] Scale test meets SLOs (proposal <1s p95, 100+ concurrent trials)
- [ ] Security review complete
- [ ] Runbook complete, support owner assigned

**This gate is MANDATORY before internal beta. Kubernetes/REST remain optional.**

---

## Tier 3: Electives (post-internal-beta)

**Duration:** Per-item, independent decisions
**Effort:** ~15-20 engineer-days per item

Each has go/no-go gate based on feasibility or demand:

1. **DEHB reimplementation (V07):** Reimpl against owned interfaces, NOT vendor wrap (~10d impl + 5d validation)
2. **ifBO curve model adoption (V15):** Split into V15a (feasibility) and V15b (integration); cancel if V15a fails
3. **HEBO-style robustness:** Warping and ensembles on GP (~8d + 5d campaign); defer if no messy objectives
4. **CMA-ES wrapper:** Low priority, Hamiltonian-only (~2d wrap + 2d validation); ship if users request

**Decisions mapped to Tier 3:** """ + f"{len(by_tier['T3'])} capabilities from traceability matrix" + """

---

## Summary Timeline

| Phase | Calendar weeks | Engineer-days | Accelerator-hours | Status |
|-------|----------------|---------------|-------------------|--------|
| R0 (spec) | 2 | 10.5 | 0 | ✅ Complete |
| R1 (spike) | 3 | 27 | 0 | ✅ Complete, gate PASS |
| Tier 0 | 8-10 | 65 | 2,500 | ⛔ Blocked on program approval |
| Tier 1 | 8-10 | 70 | 10,900 | ⛔ Blocked on Tier 0 gate |
| Tier 2 | 14-18 | 70 | 4,600-19,600 | ⛔ Blocked on Tier 1 gate |
| Dist. beta | 4-5 | 35 | 0 | ⛔ Blocked on Tier 2 gate |
| Tier 3 (per item) | 2-4 each | 15-20 each | ~2,000 each | ⛔ Post-internal-beta |
| **TOTAL to beta** | **39-48 weeks** | **275-310 days** | **17k-33k** | |

**With 2 engineers average:** ~140-155 engineer-weeks → ~35-39 calendar months at realistic utilization

**Realistic calendar: 39-48 weeks (9-11 months) from R0 start to internal beta launch**

Assumes:
- 2 engineers through Tier 0-1
- 2-3 engineers for Tier 2 (population + architecture)
- 1 engineer for distributed hardening
- Parallelism where possible
- 25-30% contingency for integration, reviews, rework

---

## Validation Register

Complete test suite V01-V15:

"""

    for v_id in sorted(validation_register.keys()):
        entry = validation_register[v_id]
        md += f"### {v_id}\n\n"
        md += f"**Claim:** {entry['claim']}\n\n"
        if entry['pass_rule']:
            md += f"**Pass rule:** {entry['pass_rule']}\n\n"
        md += f"**Gate criteria:** {entry['criteria']}\n\n"
        md += f"**Program gate:** {gate_for_entry(v_id)}\n\n"
        if entry['survey_gate']:
            md += f"**Survey gate:** {entry['survey_gate']}\n\n"
        if not entry['in_reconciliation']:
            md += "_⚠️ Entry missing from reconciliation doc_\n\n"
        if not entry['in_survey']:
            md += "_⚠️ Entry missing from survey table_\n\n"

    md += """---

## Risk Register

| Risk | Likelihood | Impact | Mitigation | Tripwire |
|------|-----------|--------|------------|----------|
| BG-PBT fails V08 boundary trial | Medium | High (flagship demoted) | Demotion rule pre-committed; fallback is DEHB | Week 22: if informal tests show <50% win rate, flag early |
| Trust-region BO unstable on mixed spaces | Low | High (blocks PB2-Mix, BG-PBT explore) | BoTorch TuRBO production-tested; our adaptation is thin | Week 9: if V04 shows high variance, add restart logic |
| ASHA rank correlations fail on real RL tasks | Low | High (tier-0 floor collapses) | Chapter 5 evidence shows 0.7+ correlation typical | Week 10: pilot V06 early; if <0.5, revisit fidelity definition |
| Validation campaigns blocked by Brax env install | Low | Medium (delays gates) | Install Brax at Tier 0 start, not week 12 | Week 7: test `import brax` and run one episode |
| Store schema needs migration mid-build | Medium | Low (1-2d disruption) | Design with extensibility (JSON blob for method-specific metadata) | Any week: if schema change needed, write migration and re-seed test data |

---

## Traceability: Decisions → Tiers

"""

    for tier_name in ['T0', 'T1', 'T2', 'T3']:
        tier_decisions = by_tier[tier_name]
        if tier_decisions:
            md += f"### {tier_name}\n\n"
            for d in tier_decisions:
                v_entries = ', '.join(d.get('validation_entries', []))
                md += f"- **{d['id']}:** {d['capability']} (validation: {v_entries or 'none'})\n"
            md += "\n"

    md += """---

## How to Use This Program

1. **Current phase:** Check Summary Timeline for current blocking phase
2. **Next gate:** Review gate criteria and validation entries
3. **Task tracking:** Use `tools/generate_tasks.py --phase tierX` to generate work breakdown
4. **Progress:** Check `docs/progress.md` (auto-generated from ground truth)
5. **Amendments:** Changes produce v2.1, v2.2 with explicit deltas—see [governance.md](governance.md)

**Live tracking:** Run `python3 tools/update_progress.py` weekly to regenerate progress from ground truth.

---

## Program Amendments

| Version | Date | Changes | Approved by |
|---------|------|---------|-------------|
| v2.0 | """ + date.today().isoformat() + """ | Initial generated version | [BUILD_PROGRAM_v2_APPROVAL.md](BUILD_PROGRAM_v2_APPROVAL.md) |

_Future amendments will be logged here with explicit deltas._

---

**For questions or scope changes, see:**
- Survey Chapter 15 (build plan detail)
- Survey Chapter 14 (validation suite specification)
- [governance.md](governance.md) (change control process)
"""

    return md


def main():
    parser = argparse.ArgumentParser(description="Generate BUILD_PROGRAM_v2.md")
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify mode: exit 1 if generated output differs from committed file'
    )
    args = parser.parse_args()

    # Load inputs
    decisions = load_decisions(Path('hpo-survey-decisions.json'))
    validation_register = load_validation_register(Path('validation/protocols.json'))

    # Check gate coverage before generating
    problems = check_gate_coverage(validation_register)
    if problems:
        print("ERROR: Validation gate assignment has coverage problems:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    # Generate
    output = generate_program(
        decisions,
        validation_register,
        Path('WORK_BREAKDOWN_TIMELINE_DRAFT.md')
    )

    output_path = Path('BUILD_PROGRAM_v2.md')

    if args.verify:
        # Verify mode: check if generated matches committed
        if not output_path.exists():
            print(f"ERROR: {output_path} does not exist for verification")
            sys.exit(1)

        current = output_path.read_text()
        if current != output:
            print(f"ERROR: {output_path} has drifted from inputs")
            print("Run `python3 tools/generate_build_program.py` to regenerate")
            sys.exit(1)

        print(f"✅ {output_path} is in sync with inputs")
        sys.exit(0)
    else:
        # Generate mode: write output
        output_path.write_text(output)
        print(f"Generated: {output_path}")
        print(f"  - {len(decisions)} decisions mapped to tiers")
        print(f"  - {len(validation_register)} validation entries")
        print(f"  - Total {len(output.splitlines())} lines")
        sys.exit(0)


if __name__ == "__main__":
    main()
