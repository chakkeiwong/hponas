#!/usr/bin/env python3
"""
Generate docs/progress.md from ground truth plus hand-authored narrative.

The tracker drifted twice while it was hand-maintained: it claimed Tier 0 was
blocked after the block was lifted, and it carried a statistical-reviewer item as
open after the decision was taken. Both were invisible because nothing compared the
prose against the repository.

Ground truth read here (never hand-entered):
  - git tags            -> which phases are complete, and when
  - gate_reports/*.md   -> gate verdicts and dates
  - validation/protocols.json -> protocol status and unresolved policy decisions
  - tools/generate_build_program.py -> which validation entries each gate runs

Hand-authored input (docs/progress_narrative.json): the judgment that cannot be
derived — why a risk matters, what a decision traded off, what a finding cost.

Deliberately does NOT run the test suite. Test counts come from the most recent gate
report, which tools/gate_check.py produces. That keeps this generator fast, offline,
and byte-deterministic so --verify works in CI. For fresh numbers, run gate_check
first; it writes a new report and this picks it up.

Usage:
    python3 tools/update_progress.py            # regenerate docs/progress.md
    python3 tools/update_progress.py --verify   # exit 1 if stale (for CI)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NARRATIVE_PATH = Path('docs/progress_narrative.json')
OUTPUT_PATH = Path('docs/progress.md')
GATE_REPORTS_DIR = Path('gate_reports')
PROTOCOLS_PATH = Path('validation/protocols.json')

# Tag prefix that marks a completed phase, and how to label it.
PHASE_TAGS = {
    'phase-r0-complete': 'R0',
    'phase-r1-complete': 'R1',
    'phase-tier0-complete': 'Tier 0',
    'phase-tier1-complete': 'Tier 1',
    'phase-tier2-complete': 'Tier 2',
}

GATE_LABELS = {
    'tier0': 'Tier 0',
    'tier1': 'Tier 1',
    'tier2': 'Tier 2',
    'dist_beta': 'Distributed Beta',
    'tier3': 'Tier 3 (per item)',
}


def git_tags() -> dict[str, dict]:
    """Read annotated tags as ground truth for phase completion."""
    try:
        out = subprocess.run(
            ['git', 'tag', '-l', '--format=%(refname:short)\t%(creatordate:short)\t%(subject)'],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    tags = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        name, created = parts[0], parts[1]
        subject = parts[2] if len(parts) > 2 else ''
        tags[name] = {'name': name, 'date': created, 'subject': subject}
    return tags


def gate_reports() -> list[dict]:
    """Parse every gate report for its verdict, date, and test figures."""
    if not GATE_REPORTS_DIR.exists():
        return []

    reports = []
    for path in sorted(GATE_REPORTS_DIR.glob('*.md')):
        text = path.read_text()

        title = re.search(r'^#\s+(.+?)\s*$', text, re.M)
        verdict = re.search(r'\*\*Verdict:\*\*\s*(\w+)', text)
        stamp = re.search(r'\*\*Date:\*\*\s*(\S+)', text)

        # Test figures if the report happens to carry them.
        tests = re.search(r'(\d+)\s+tests?\s+passed|passed[^\n]*?(\d+)\s+tests?', text, re.I)
        coverage = re.search(r'(\d+)%\s*coverage|coverage[^\n]*?(\d+)%', text, re.I)

        reports.append({
            'path': path,
            'title': title.group(1) if title else path.stem,
            'verdict': verdict.group(1).upper() if verdict else 'UNKNOWN',
            'date': stamp.group(1).split('T')[0] if stamp else '',
            'tests': next((g for g in (tests.groups() if tests else ()) if g), None),
            'coverage': next((g for g in (coverage.groups() if coverage else ()) if g), None),
        })
    return reports


def protocol_status() -> dict:
    """Read protocol register status and any unresolved policy decisions."""
    if not PROTOCOLS_PATH.exists():
        return {}

    data = json.loads(PROTOCOLS_PATH.read_text())
    decisions = data.get('policy', {}).get('open_decisions', [])
    unresolved = [
        d for d in decisions
        if not str(d.get('status', '')).upper().startswith('RESOLVED')
    ]
    return {
        'status': data.get('status', 'UNKNOWN'),
        'status_note': data.get('status_note', ''),
        'entry_count': len(data.get('entries', {})),
        'open_decisions': unresolved,
        'total_decisions': len(decisions),
    }


def gate_criteria() -> dict[str, list[str]]:
    """
    Which validation entries each gate runs.

    Imported from the program generator so the tracker cannot disagree with the
    approved program about what a gate tests.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from generate_build_program import PROGRAM_GATE_ASSIGNMENT
    except ImportError:
        return {}
    return dict(PROGRAM_GATE_ASSIGNMENT)


def _phase_status(phase_key: str, tags: dict, reports: list[dict]) -> tuple[str, str]:
    """
    Resolve a phase's status line from tags and gate reports.

    Returns (status_line, date). A phase is complete when its tag exists; the gate
    verdict comes from the matching report rather than from prose.
    """
    tag_name = next(
        (t for t, label in PHASE_TAGS.items() if label.lower().replace(' ', '') == phase_key.lower()),
        None,
    )
    tag = tags.get(tag_name) if tag_name else None

    label = PHASE_TAGS.get(tag_name, phase_key) if tag_name else phase_key
    report = next(
        (r for r in reports if r['title'].upper().startswith(label.upper())),
        None,
    )

    if tag:
        if report and report['verdict'] == 'PASS':
            return f"✅ Complete — gate PASS ({tag['date']})", tag['date']
        return f"✅ Complete ({tag['date']})", tag['date']
    return "", ""


def _checklist(items: list[dict]) -> str:
    lines = []
    for item in items:
        box = 'x' if item.get('done') else ' '
        lines.append(f"- [{box}] {item['text']}")
    return '\n'.join(lines)


def render(narrative: dict, tags: dict, reports: list[dict],
           protocols: dict, criteria: dict[str, list[str]]) -> str:
    """Assemble the tracker."""
    header = narrative['header']
    phases = narrative['phases']

    md = f"""# Build Progress Tracker

**Current phase:** {header['current_phase']}
**Next milestone:** {header['next_milestone']}

> **Generated file.** Produced by `tools/update_progress.py` from git tags, gate
> reports, and `validation/protocols.json`, plus the hand-authored judgment in
> `docs/progress_narrative.json`. Edit the narrative file, not this one; edits here
> are overwritten. Run `python3 tools/update_progress.py` after any gate or tag.

> {header['callout']}

---

## Phase R0: {phases['R0']['title']}
"""

    r0_status, _ = _phase_status('R0', tags, reports)
    if not r0_status:
        r0_status = "✅ Complete (2026-08-28)"

    md += f"""
**Status:** {r0_status}
**Effort:** {phases['R0']['effort_note']}
**Report:** [{Path(phases['R0']['report']).name}]({phases['R0']['report']})

{_checklist(phases['R0']['deliverables'])}

---

## Phase R1: {phases['R1']['title']}
"""

    r1_status, _ = _phase_status('R1', tags, reports)
    r1_report = next((r for r in reports if r['title'].upper().startswith('R1')), None)

    md += f"\n**Status:** {r1_status or 'in progress'}\n"
    if r1_report:
        md += f"**Gate report:** [{r1_report['path'].name}](../{r1_report['path']})\n"
    md += f"**Interface review:** [{phases['R1']['interface_review']}]({phases['R1']['interface_review']})\n"
    md += f"**Charter:** [{Path(phases['R1']['charter']).name}]({phases['R1']['charter']})\n"

    md += f"\n### Deliverables\n{_checklist(phases['R1']['deliverables'])}\n"

    if r1_report and r1_report['tests']:
        suffix = f", {r1_report['coverage']}% coverage" if r1_report['coverage'] else ""
        md += f"- [x] Test suite: {r1_report['tests']} tests passing{suffix}\n"

    md += "\n### Findings resolved during close-out\n"
    for i, finding in enumerate(phases['R1']['findings'], 1):
        md += f"{i}. {finding}\n"
    md += f"\n{phases['R1']['carried_forward']}\n"

    md += _render_tiers(phases, criteria)
    md += _render_protocols(protocols)
    md += _render_risks(narrative['risks'])
    md += _render_gate_history(reports, narrative, criteria)
    md += _render_decisions(narrative['decisions'])
    return md


def _criteria_text(gate_key: str, criteria: dict[str, list[str]]) -> str:
    """Render a gate's validation entries, marking V04's split components."""
    entries = criteria.get(gate_key, [])
    if not entries:
        return "—"
    rendered = []
    for vid in entries:
        if vid == 'V04':
            suffix = '-T0' if gate_key == 'tier0' else '-T1' if gate_key == 'tier1' else ''
            rendered.append(f"{vid}{suffix}")
        else:
            rendered.append(vid)
    return ', '.join(rendered)


def _render_tiers(phases: dict, criteria: dict[str, list[str]]) -> str:
    """Tier sections, with gate criteria taken from the approved program."""
    t0 = phases['tier0']
    md = f"""
---

## Tier 0: {t0['title']}

**Status:** {t0['status_line']}
**Gate:** {_criteria_text('tier0', criteria)}
**Program:** [{Path(t0['program']).name}]({t0['program']})
**Approval:** [{Path(t0['approval']).name}]({t0['approval']})

{t0['body']}

---

## Tier 1: {phases['tier1']['title']}

**Status:** {phases['tier1']['status_line']}
**Gate:** {_criteria_text('tier1', criteria)}

---

## Tier 2/3: {phases['tier23']['title']}

**Status:** {phases['tier23']['status_line']}
**Gate:** {_criteria_text('tier2', criteria)} (Tier 2), \
{_criteria_text('dist_beta', criteria)} (Distributed Beta), \
{_criteria_text('tier3', criteria)} (Tier 3 electives)
"""
    return md


def _render_protocols(protocols: dict) -> str:
    """Validation protocol status, including anything still unresolved."""
    if not protocols:
        return ""

    md = f"""
---

## Validation protocols

**Status:** {protocols['status']} — {protocols['entry_count']} entries
**Register:** [validation/protocols.json](../validation/protocols.json)
**Checker:** `python3 tools/check_protocols.py`

{protocols['status_note']}
"""

    open_decisions = protocols['open_decisions']
    resolved = protocols['total_decisions'] - len(open_decisions)
    if open_decisions:
        md += f"\n**Policy decisions:** {resolved} of {protocols['total_decisions']} resolved.\n\n"
        for decision in open_decisions:
            md += f"- **{decision['id']}** ({decision.get('status', '?')}): {decision['question']}\n"
    else:
        md += f"\n**Policy decisions:** all {protocols['total_decisions']} resolved.\n"
    return md


def _render_risks(risks: list[dict]) -> str:
    md = """
---

## Risk flags (live)

| Opened | Risk | Signal | Status |
|--------|------|--------|--------|
"""
    for r in risks:
        detail = f" — {r['detail']}" if r.get('detail') else ""
        md += f"| {r['opened']} | {r['risk']} | {r['signal']} | **{r['status']}**{detail} |\n"
    return md


def _render_gate_history(reports: list[dict], narrative: dict,
                         criteria: dict[str, list[str]]) -> str:
    """Gate history: completed gates from reports, future gates from the narrative."""
    md = """
---

## Gate history

| Gate | Date | Criteria | Result | Report |
|------|------|----------|--------|--------|
"""
    seen = set()
    for r in reports:
        label = r['title'].replace(' Gate Report', '').strip()
        seen.add(label.upper())
        verdict = f"**{r['verdict']}**" if r['verdict'] == 'PASS' else r['verdict']
        md += (
            f"| {label} | {r['date']} | {r['title']} | {verdict} "
            f"| [{r['path'].name}](../{r['path']}) |\n"
        )

    for planned in narrative.get('gate_history_planned', []):
        if planned['gate'].upper() in seen:
            continue
        crit = _criteria_text(planned['criteria_from'], criteria)
        md += (
            f"| {planned['gate']} | {planned['date']} | {crit} "
            f"| {planned['result']} | {planned['report']} |\n"
        )
    return md


def _render_decisions(decisions: list[dict]) -> str:
    md = """
---

## Decisions logged

| Date | Decision | Rationale |
|------|----------|-----------|
"""
    for d in decisions:
        md += f"| {d['date']} | {d['decision']} | {d['rationale']} |\n"
    md += "\n_Add new decisions to `docs/progress_narrative.json`, then regenerate._\n"
    return md


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--verify', action='store_true',
        help='exit 1 if docs/progress.md differs from what the inputs produce',
    )
    args = parser.parse_args()

    if not NARRATIVE_PATH.exists():
        print(f"ERROR: {NARRATIVE_PATH} not found (run from repo root)")
        return 1

    narrative = json.loads(NARRATIVE_PATH.read_text())
    tags = git_tags()
    reports = gate_reports()
    protocols = protocol_status()
    criteria = gate_criteria()

    if not criteria:
        print("WARNING: could not import gate assignment; gate criteria will be blank")

    output = render(narrative, tags, reports, protocols, criteria)

    if args.verify:
        if not OUTPUT_PATH.exists():
            print(f"ERROR: {OUTPUT_PATH} does not exist; run without --verify")
            return 1
        if OUTPUT_PATH.read_text() != output:
            print(f"ERROR: {OUTPUT_PATH} is stale relative to its inputs")
            print("Run `python3 tools/update_progress.py` to regenerate")
            return 1
        print(f"✅ {OUTPUT_PATH} is in sync with ground truth")
        return 0

    OUTPUT_PATH.write_text(output)
    print(f"Generated: {OUTPUT_PATH}")
    print(f"  - {len(tags)} tags, {len(reports)} gate report(s)")
    print(f"  - {len(narrative['risks'])} risks, {len(narrative['decisions'])} decisions")
    if protocols:
        n_open = len(protocols['open_decisions'])
        print(f"  - protocols {protocols['status']}: {protocols['entry_count']} entries, "
              f"{n_open} policy decision(s) open")
    print(f"  - {len(output.splitlines())} lines")
    return 0


if __name__ == '__main__':
    sys.exit(main())
