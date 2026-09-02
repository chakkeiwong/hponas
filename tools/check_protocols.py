#!/usr/bin/env python3
"""
Validate validation/protocols.json for completeness and internal consistency.

This is the mechanical check that finding F1 was missing. The accepted per-entry
corrections in RESPONSE_TO_CODEX_REVIEW.md were granular and correct, but nothing
compared them against the chapter, so the chapter drifted and the drift went unnoticed
until review. This tool makes that class of drift a build failure.

What it enforces:
  1. Every entry carries the fields a campaign implementer needs to reproduce the
     decision: estimand, endpoint, repetition unit, max sample, missingness rule,
     stopping rule, release consequence.
  2. Alpha bookkeeping is consistent both ways. An entry either belongs to a declared
     confirmatory family or explicitly declares why it consumes no alpha; a family's
     stated size matches its actual membership.
  3. Any entry carrying a decision margin also carries a written justification for it,
     since a margin is a product tolerance and cannot be read off observed noise.
  4. Any entry that can return "inconclusive" says what that means for release.
  5. Power targets match the policy, including the asymmetric high-power entries.
  6. Every protocol entry maps to a gate the program actually runs, and every gate the
     program runs has protocol records behind it.

Usage:
    python3 tools/check_protocols.py            # report and exit nonzero on problems
    python3 tools/check_protocols.py --quiet    # exit code only
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROTOCOLS_PATH = Path('validation/protocols.json')
CHAPTER_PATH = Path('hpo-survey/sections/16-validation.tex')

# Rules the accepted corrections retired. Each may still be *discussed* in the chapter
# (the amendments explain why each was wrong, which is worth keeping), but may not
# reappear as an active rule. The guard is proximity to a retirement marker: prose that
# introduces one of these without framing it as retired is drift.
#
# This is the check that finding F1 needed and did not have. Five entries had already
# been corrected on paper while the chapter still carried the superseded rule.
RETIRED_RULES = [
    (r'0\.5\\%', 'V01 fixed 0.5% tolerance band (replaced by distributional comparison)'),
    (r'clears \$0\.6\$|lower bound clears \$0\.6\$',
     'V10 gating on Spearman rho >= 0.6 (replaced by false-cull and recall bounds)'),
    (r'single fixed seed',
     'V10 single-seed design (replaced by 5 seeds per configuration)'),
    (r'visual\s+inspection',
     'V13 visual multimodality inspection (replaced by automated diagnostics)'),
    (r'within one standard error',
     'V13 one-standard-error agreement check (replaced by simultaneous MCSE bands)'),
    (r'if the interval overlaps',
     'V09 demotion on marginal-interval overlap (replaced by a paired test)'),
    (r'threshold applies to accelerator-seconds',
     'V06 threshold on accelerator-seconds with queue folded in (replaced by billed resource-seconds)'),
    (r'\$\\alpha = 0\.05\$ uncorrected',
     'uncorrected per-entry primary alpha (replaced by per-gate Holm-Bonferroni)'),
]

RETIREMENT_MARKERS = [
    'earlier draft', 'no longer', 'replaced', 'superseded',
    'an earlier version', 'that draft', 'wrong instrument',
]

# How far from an occurrence a retirement marker may sit and still frame it.
RETIREMENT_WINDOW = 700

# Fields every entry must carry, whatever its class.
REQUIRED_ALL = [
    'id', 'gate', 'class', 'claim', 'estimand', 'test', 'comparators',
    'primary_endpoint', 'repetition_unit', 'task_scope', 'max_sample',
    'missingness', 'stopping_rule', 'release_consequence',
]

# Additional fields required of entries that consume family alpha.
REQUIRED_CONFIRMATORY = [
    'sidedness', 'direction', 'alpha_family', 'power_target', 'scale_bounds',
]

# Classes that make no inferential ranking claim and so carry no alpha.
CLASSES_NO_ALPHA = {
    'deterministic_veto',
    'reproduction_check',
    'deterministic_veto_plus_calibration',
}

# Verdicts that oblige the entry to say what happens to the capability.
CONSEQUENCE_KEYS_MIN = {'pass', 'fail'}


def check_required_fields(entries: dict) -> list[str]:
    """Every entry carries the fields needed to run and decide it."""
    problems = []
    for vid, entry in entries.items():
        for field in REQUIRED_ALL:
            if field not in entry or entry[field] in (None, "", []):
                problems.append(f"{vid}: missing required field '{field}'")

        if entry.get('class') in CLASSES_NO_ALPHA:
            continue

        for field in REQUIRED_CONFIRMATORY:
            if field not in entry or entry[field] in (None, "", []):
                problems.append(
                    f"{vid}: confirmatory entry missing '{field}' "
                    f"(class={entry.get('class')!r})"
                )
    return problems


def check_alpha_families(data: dict) -> list[str]:
    """Alpha bookkeeping is consistent in both directions."""
    problems = []
    entries = data['entries']
    families = data['policy']['confirmatory_families']['families']

    declared: dict[str, str] = {}
    for fam_name, fam in families.items():
        members = fam.get('members', [])
        structure = fam.get('structure', 'simultaneous')
        stated_m = fam.get('m')

        if structure == 'fixed_sequence':
            # A fixed sequence spends alpha once: each hypothesis is only reached when
            # the previous one rejected, so the correction denominator is 1 regardless
            # of membership. This only holds if the order is prespecified.
            if stated_m != 1:
                problems.append(
                    f"family {fam_name}: fixed_sequence family must state m=1, got {stated_m}"
                )
            sequence = fam.get('sequence')
            if not sequence:
                problems.append(
                    f"family {fam_name}: fixed_sequence family must declare 'sequence' "
                    f"(the order is what makes the error control valid)"
                )
            elif sorted(sequence) != sorted(members):
                problems.append(
                    f"family {fam_name}: sequence {sequence} does not match "
                    f"members {members}"
                )
        elif structure == 'simultaneous':
            if stated_m is not None and stated_m != len(members):
                problems.append(
                    f"family {fam_name}: states m={stated_m} but lists "
                    f"{len(members)} members"
                )
        else:
            problems.append(
                f"family {fam_name}: unknown structure {structure!r} "
                f"(expected 'simultaneous' or 'fixed_sequence')"
            )

        for member in members:
            if member in declared:
                problems.append(
                    f"{member}: appears in two families ({declared[member]}, {fam_name})"
                )
            declared[member] = fam_name

            if member not in entries:
                problems.append(
                    f"family {fam_name}: member {member} has no protocol entry"
                )

    for vid, entry in entries.items():
        fam = entry.get('alpha_family')
        no_alpha = entry.get('class') in CLASSES_NO_ALPHA

        if fam is None:
            if not no_alpha:
                problems.append(
                    f"{vid}: alpha_family is null but class={entry.get('class')!r} "
                    f"is not in the no-alpha classes"
                )
            elif not entry.get('alpha_note'):
                problems.append(
                    f"{vid}: consumes no alpha but has no alpha_note explaining why"
                )
            if vid in declared:
                problems.append(
                    f"{vid}: alpha_family is null but it is listed in family {declared[vid]}"
                )
            continue

        if fam not in families:
            problems.append(f"{vid}: alpha_family {fam!r} is not a declared family")
        elif vid not in declared:
            problems.append(
                f"{vid}: claims alpha_family {fam!r} but is not among its members"
            )
        elif declared[vid] != fam:
            problems.append(
                f"{vid}: claims alpha_family {fam!r} but is listed under {declared[vid]!r}"
            )

    return problems


def check_margins(entries: dict) -> list[str]:
    """A decision margin is a product tolerance and needs a written justification."""
    problems = []
    for vid, entry in entries.items():
        if 'margin' not in entry:
            continue
        if not entry.get('margin_justification'):
            problems.append(
                f"{vid}: declares margin={entry['margin']} with no margin_justification"
            )
        margin = entry['margin']
        if not isinstance(margin, (int, float)) or margin < 0:
            problems.append(f"{vid}: margin {margin!r} is not a non-negative number")
    return problems


def check_consequences(entries: dict) -> list[str]:
    """Every reachable verdict says what happens to the capability."""
    problems = []
    for vid, entry in entries.items():
        consequence = entry.get('release_consequence')
        if not isinstance(consequence, dict):
            problems.append(f"{vid}: release_consequence is not an object")
            continue

        missing = CONSEQUENCE_KEYS_MIN - set(consequence)
        if missing:
            problems.append(
                f"{vid}: release_consequence missing {sorted(missing)}"
            )

        # An entry sized by a power calculation can exhaust its budget without
        # deciding, so it must say what that means. V08 answers this with 'hold'.
        if entry.get('power_target') is not None:
            if 'inconclusive' not in consequence and 'hold' not in consequence:
                problems.append(
                    f"{vid}: has a power target and so can exhaust max_sample, but "
                    f"release_consequence declares neither 'inconclusive' nor 'hold'"
                )

        # A hold that parks a capability next to a release decision needs an owner,
        # an expiry, and funding, or it becomes permanent by neglect.
        if 'hold' in consequence:
            required = entry.get('hold_requires')
            if not required:
                problems.append(
                    f"{vid}: allows a 'hold' verdict without declaring hold_requires "
                    f"(named owner, expiry, funded follow-up)"
                )
    return problems


def check_power_targets(data: dict) -> list[str]:
    """Power targets follow the declared policy, including the asymmetric entries."""
    problems = []
    policy = data['policy']['power']
    default = policy['default_target']
    high = policy['high_target']
    high_entries = set(policy.get('high_target_entries', []))

    for vid, entry in data['entries'].items():
        target = entry.get('power_target')
        if target is None:
            continue

        if vid in high_entries:
            if target != high:
                problems.append(
                    f"{vid}: listed in high_target_entries but power_target={target} "
                    f"(expected {high})"
                )
            elif not entry.get('power_note'):
                problems.append(
                    f"{vid}: carries the raised power target with no power_note "
                    f"explaining the asymmetric cost"
                )
        elif target not in (default, high):
            problems.append(
                f"{vid}: power_target={target} is neither the default ({default}) "
                f"nor the high target ({high})"
            )
        elif target == high:
            problems.append(
                f"{vid}: uses the high power target but is not in high_target_entries; "
                f"either add it with a rationale or use the default"
            )
    return problems


def _base_id(vid: str) -> str:
    """Map a split entry id back to its program-level id (V04-T0 -> V04, V11a -> V11)."""
    for suffix in ('-T0', '-T1'):
        if vid.endswith(suffix):
            return vid[: -len(suffix)]
    if len(vid) == 4 and vid[-1] in 'ab':
        return vid[:3]
    return vid


def check_program_alignment(entries: dict) -> list[str]:
    """
    Every protocol entry maps to a gate the program runs, and vice versa.

    Imports the gate map from the program generator so the two cannot drift: the
    generator is the program-side authority and this register is the statistics-side
    authority, and they have to agree on which entries run where.
    """
    problems = []
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from generate_build_program import PROGRAM_GATE_ASSIGNMENT
    except ImportError as exc:
        return [f"could not import gate map from generate_build_program: {exc}"]

    gate_name_map = {
        'tier0_remediation': 'tier0_remediation',
        'tier0_gate': 'tier0',
        'tier1_gate': 'tier1',
        'tier2_gate': 'tier2',
        'dist_beta_gate': 'dist_beta',
        'tier3_per_item': 'tier3',
    }

    program_ids = {
        _base_id(vid) for entries_ in PROGRAM_GATE_ASSIGNMENT.values() for vid in entries_
    }
    protocol_ids = {_base_id(vid) for vid in entries}

    for base in sorted(protocol_ids - program_ids):
        problems.append(
            f"{base}: has protocol records but no gate in BUILD_PROGRAM runs it"
        )
    for base in sorted(program_ids - protocol_ids):
        problems.append(
            f"{base}: is assigned to a program gate but has no protocol record"
        )

    for vid, entry in entries.items():
        gate = entry.get('gate')
        program_gate = gate_name_map.get(gate)
        if program_gate is None:
            problems.append(f"{vid}: gate {gate!r} is not a known program gate")
            continue
        # Check if this exact vid (or its base) is in the program gate
        assigned = PROGRAM_GATE_ASSIGNMENT.get(program_gate, [])
        if vid not in assigned and _base_id(vid) not in assigned:
            problems.append(
                f"{vid}: protocol assigns it to {gate}, but BUILD_PROGRAM runs "
                f"{_base_id(vid)} at {[g for g, v in PROGRAM_GATE_ASSIGNMENT.items() if vid in v or _base_id(vid) in v]}"
            )

    return problems


def check_retired_rules() -> list[str]:
    """
    The chapter may explain a retired rule but may not carry it as an active one.

    Finding F1 was a set of retired rules still sitting in the chapter as live text.
    Nothing compared the accepted corrections against the prose, so the drift survived
    until external review. This check closes that loop: each retired rule must appear
    within RETIREMENT_WINDOW characters of a marker that frames it as superseded.
    """
    problems = []
    if not CHAPTER_PATH.exists():
        return [f"{CHAPTER_PATH} not found; cannot check for retired rules"]

    text = CHAPTER_PATH.read_text()
    lowered = text.lower()

    for pattern, description in RETIRED_RULES:
        for match in re.finditer(pattern, text, re.I):
            start = max(0, match.start() - RETIREMENT_WINDOW)
            window = lowered[start : match.end() + RETIREMENT_WINDOW]
            if any(marker in window for marker in RETIREMENT_MARKERS):
                continue
            line = text.count('\n', 0, match.start()) + 1
            problems.append(
                f"{CHAPTER_PATH}:{line}: retired rule present without a retirement "
                f"marker — {description}"
            )
    return problems


def check_entries_documented() -> list[str]:
    """Every register entry is discussed in the chapter, so neither can drop the other."""
    problems = []
    if not CHAPTER_PATH.exists():
        return []

    text = CHAPTER_PATH.read_text()
    data = json.loads(PROTOCOLS_PATH.read_text())

    for vid in data['entries']:
        # Split entries (V04-T0, V11a) are discussed under their base id in prose.
        base = _base_id(vid)
        if base not in text:
            problems.append(f"{base}: in the protocol register but absent from the chapter")
    return problems


def check_open_decisions(data: dict) -> list[str]:
    """Open policy decisions are surfaced, not silently defaulted."""
    problems = []
    for decision in data['policy'].get('open_decisions', []):
        for field in ('id', 'question', 'chosen', 'status'):
            if not decision.get(field):
                problems.append(
                    f"open decision {decision.get('id', '?')}: missing '{field}'"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quiet', action='store_true', help='exit code only')
    args = parser.parse_args()

    if not PROTOCOLS_PATH.exists():
        print(f"ERROR: {PROTOCOLS_PATH} not found (run from repo root)")
        return 1

    data = json.loads(PROTOCOLS_PATH.read_text())
    entries = data['entries']

    checks = [
        ("required fields", check_required_fields(entries)),
        ("alpha families", check_alpha_families(data)),
        ("margin justifications", check_margins(entries)),
        ("release consequences", check_consequences(entries)),
        ("power targets", check_power_targets(data)),
        ("program alignment", check_program_alignment(entries)),
        ("retired rules absent", check_retired_rules()),
        ("entries documented", check_entries_documented()),
        ("open decisions", check_open_decisions(data)),
    ]

    total = sum(len(problems) for _, problems in checks)

    if args.quiet:
        return 1 if total else 0

    print(f"Protocol register: {PROTOCOLS_PATH}")
    print(f"Status: {data.get('status')} — {len(entries)} entries\n")

    for name, problems in checks:
        if problems:
            print(f"FAIL  {name} ({len(problems)})")
            for problem in problems:
                print(f"        {problem}")
        else:
            print(f"ok    {name}")

    print()
    if total:
        print(f"{total} problem(s) found.")
        return 1

    open_count = sum(
        1 for d in data['policy'].get('open_decisions', [])
        if d.get('status', '').startswith('OPEN')
    )
    print("All checks passed.")
    if open_count:
        print(
            f"{open_count} open policy decision(s) still require sign-off "
            f"before confirmatory campaigns; see policy.open_decisions."
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
