#!/usr/bin/env python3
"""
Verify BUILD_PROGRAM_v2.md validation register matches validation/protocols.json.

BUILD_PROGRAM may use aggregate entries (V04, V11, V15) that cover multiple protocol
entries (V04-T0/V04-T1, V11a/V11b, V15a/V15b). This checker verifies coverage rather
than exact 1:1 mapping: every protocol entry must be mentioned in BUILD_PROGRAM.

Exit codes:
    0 - in sync
    1 - drift detected
"""

import json
import re
import sys
from pathlib import Path


def load_protocols_register(protocols_path: Path) -> dict[str, dict]:
    """Extract validation entries from protocols.json."""
    with open(protocols_path) as f:
        data = json.load(f)

    entries = data.get('entries', {})
    register = {}

    for vid, entry in entries.items():
        register[vid] = {
            'id': vid,
            'claim': entry.get('claim', ''),
        }

    return register


def extract_program_register(program_path: Path) -> dict[str, dict]:
    """Extract validation register from BUILD_PROGRAM_v2.md."""
    with open(program_path) as f:
        text = f.read()

    match = re.search(
        r'## Validation Register.*?(?=^## |\Z)',
        text,
        re.MULTILINE | re.DOTALL
    )

    if not match:
        print("ERROR: Could not find '## Validation Register' section")
        return {}

    section = match.group(0)
    register = {}

    pattern = r'### (V\d\d[a-z]?(?:-T[01])?)\s+\*\*Claim:\*\* ([^\n]+)'
    for vid, claim in re.findall(pattern, section):
        register[vid] = {
            'id': vid,
            'claim': claim.strip(),
        }

    return register


def main():
    protocols_path = Path('validation/protocols.json')
    program_path = Path('BUILD_PROGRAM_v2.md')

    if not protocols_path.exists():
        print(f"ERROR: {protocols_path} not found")
        sys.exit(1)

    if not program_path.exists():
        print(f"ERROR: {program_path} not found")
        sys.exit(1)

    protocols_reg = load_protocols_register(protocols_path)
    program_reg = extract_program_register(program_path)

    # Map protocol entries to their BUILD_PROGRAM aggregate
    # V04-T0, V04-T1 -> V04
    # V11a, V11b -> V11
    # V15a, V15b -> V15
    def aggregate_id(vid: str) -> str:
        if vid.startswith('V04-'):
            return 'V04'
        if vid.startswith('V11'):
            return 'V11'
        if vid.startswith('V15'):
            return 'V15'
        return vid

    # Check coverage: every protocol entry must have a BUILD_PROGRAM entry
    problems = []
    covered = set()

    for proto_vid in sorted(protocols_reg):
        prog_vid = aggregate_id(proto_vid)
        if prog_vid in program_reg:
            covered.add(proto_vid)
        else:
            problems.append(
                f"{proto_vid} from protocols.json has no BUILD_PROGRAM entry "
                f"(expected {prog_vid})"
            )

    # Warn about program entries with no protocol backing
    protocol_aggregates = {aggregate_id(v) for v in protocols_reg}
    for prog_vid in sorted(program_reg):
        if prog_vid not in protocol_aggregates:
            problems.append(
                f"{prog_vid} in BUILD_PROGRAM but no matching protocol entries"
            )

    if problems:
        print("ERROR: BUILD_PROGRAM validation register drift from protocols.json:")
        for p in problems:
            print(f"  - {p}")
        print("\nFix: update BUILD_PROGRAM_v2.md or protocols.json to align")
        sys.exit(1)

    print(f"✅ BUILD_PROGRAM covers all {len(covered)} protocol entries")
    sys.exit(0)


if __name__ == "__main__":
    main()
