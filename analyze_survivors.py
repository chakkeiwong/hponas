#!/usr/bin/env python3
"""Survivor Analysis Script - Phase 3 Preparation

This script analyzes mutation survivors to identify patterns and guide test creation.
Run after R6 mutation testing completes.

Usage:
    python analyze_survivors.py [--sample N] [--module MODULE]
"""

import subprocess
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
import sys


def get_survivors() -> List[str]:
    """Extract survivor list from mutmut results."""
    result = subprocess.run(
        ['python', '-m', 'mutmut', 'results'],
        capture_output=True,
        text=True,
        timeout=60
    )

    survivors = []
    for line in result.stdout.split('\n'):
        if 'survived' in line:
            survivors.append(line.strip())

    return survivors


def parse_survivor(line: str) -> Dict[str, str]:
    """Parse survivor line into components.

    Format: hponas.module.file.xǁClassǁmethod__mutmut_N: survived
    """
    match = re.match(r'\s*hponas\.([^.]+)\.([^.]+)\.xǁ([^ǁ]+)ǁ([^_]+)__mutmut_(\d+)', line)
    if match:
        return {
            'module': match.group(1),
            'file': match.group(2),
            'class': match.group(3),
            'method': match.group(4),
            'mutid': match.group(5),
            'fullname': f"hponas.{match.group(1)}.{match.group(2)}.xǁ{match.group(3)}ǁ{match.group(4)}__mutmut_{match.group(5)}"
        }
    return None


def categorize_survivors(survivors: List[str]) -> Dict[str, List[Dict]]:
    """Group survivors by module."""
    by_module = defaultdict(list)

    for line in survivors:
        parsed = parse_survivor(line)
        if parsed:
            by_module[parsed['module']].append(parsed)

    return dict(by_module)


def analyze_methods(survivors: List[Dict]) -> Counter:
    """Count survivors by class.method."""
    methods = Counter()
    for s in survivors:
        key = f"{s['class']}.{s['method']}"
        methods[key] += 1
    return methods


def sample_survivors(module: str, survivors: List[Dict], n: int = 10) -> List[Dict]:
    """Sample N survivors from a module for detailed analysis."""
    # Prioritize methods with most survivors
    methods = analyze_methods(survivors)

    sampled = []
    for method, count in methods.most_common():
        # Get one example from each high-count method
        examples = [s for s in survivors if f"{s['class']}.{s['method']}" == method]
        if examples:
            sampled.append(examples[0])
            if len(sampled) >= n:
                break

    return sampled


def get_mutation_diff(fullname: str) -> str:
    """Get the actual mutation diff for analysis."""
    result = subprocess.run(
        ['python', '-m', 'mutmut', 'show', fullname],
        capture_output=True,
        text=True,
        timeout=10
    )
    return result.stdout


def print_analysis(categorized: Dict[str, List[Dict]]):
    """Print survivor analysis."""
    total = sum(len(survivors) for survivors in categorized.values())

    print("=" * 70)
    print(f"SURVIVOR ANALYSIS - {total} TOTAL SURVIVORS")
    print("=" * 70)
    print()

    # Sort by count descending
    sorted_modules = sorted(categorized.items(), key=lambda x: -len(x[1]))

    print("By Module:")
    for module, survivors in sorted_modules:
        count = len(survivors)
        pct = 100 * count / total
        print(f"  {module:30s} {count:3d} ({pct:5.1f}%)")

    print()
    print("=" * 70)
    print("TOP METHODS WITH SURVIVORS (by module)")
    print("=" * 70)
    print()

    for module, survivors in sorted_modules[:5]:  # Top 5 modules
        print(f"\n{module.upper()} ({len(survivors)} survivors):")
        methods = analyze_methods(survivors)
        for method, count in methods.most_common(10):
            print(f"  {method:45s} {count:3d}")


def generate_test_plan(categorized: Dict[str, List[Dict]]) -> str:
    """Generate test creation plan based on survivors."""
    plan = []
    plan.append("# Survivor Kill Plan")
    plan.append("")
    plan.append("## Priority Targets (ROI-ranked)")
    plan.append("")

    sorted_modules = sorted(categorized.items(), key=lambda x: -len(x[1]))

    for i, (module, survivors) in enumerate(sorted_modules[:5], 1):
        count = len(survivors)
        methods = analyze_methods(survivors)
        top_methods = methods.most_common(5)

        plan.append(f"### Priority {i}: {module} ({count} survivors)")
        plan.append(f"**Expected kills:** {int(count * 0.4)}-{int(count * 0.6)} with 5-10 tests")
        plan.append("")
        plan.append("**Top methods:**")
        for method, cnt in top_methods:
            plan.append(f"- {method}: {cnt} mutations")
        plan.append("")

        # Sample 3 for detailed analysis
        samples = sample_survivors(module, survivors, n=3)
        plan.append("**Sample mutations to inspect:**")
        for s in samples:
            plan.append(f"- `{s['fullname']}`")
        plan.append("")

    return "\n".join(plan)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Analyze mutation survivors')
    parser.add_argument('--sample', type=int, default=10, help='Number of survivors to sample per module')
    parser.add_argument('--module', help='Focus on specific module')
    parser.add_argument('--show-diffs', action='store_true', help='Show mutation diffs for samples')
    args = parser.parse_args()

    print("Fetching survivor data...")
    survivors = get_survivors()

    if not survivors:
        print("No survivors found or mutation testing not complete.")
        sys.exit(1)

    categorized = categorize_survivors(survivors)

    if args.module:
        if args.module not in categorized:
            print(f"Module '{args.module}' not found.")
            print(f"Available modules: {', '.join(categorized.keys())}")
            sys.exit(1)

        survivors_list = categorized[args.module]
        print(f"\n{args.module.upper()} - {len(survivors_list)} survivors\n")

        methods = analyze_methods(survivors_list)
        print("Methods:")
        for method, count in methods.most_common():
            print(f"  {method:45s} {count:3d}")

        print(f"\nSampling {args.sample} survivors for inspection:")
        samples = sample_survivors(args.module, survivors_list, args.sample)

        for s in samples:
            print(f"\n{'='*70}")
            print(f"{s['class']}.{s['method']} (mutation {s['mutid']})")
            print(f"ID: {s['fullname']}")

            if args.show_diffs:
                print("\nMutation diff:")
                diff = get_mutation_diff(s['fullname'])
                print(diff)
    else:
        # Full analysis
        print_analysis(categorized)

        print()
        print("=" * 70)
        print("GENERATING TEST PLAN")
        print("=" * 70)
        print()

        plan = generate_test_plan(categorized)
        print(plan)

        # Save plan
        with open('/tmp/survivor_kill_plan.md', 'w') as f:
            f.write(plan)
        print("\nTest plan saved to: /tmp/survivor_kill_plan.md")


if __name__ == '__main__':
    main()
