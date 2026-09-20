#!/usr/bin/env python3
"""
Analyze mutation testing results from mutmut.
Calculate kill score and identify survivors by module.
"""

import subprocess
import re
from collections import defaultdict


def get_mutation_results():
    """Get all mutation results from mutmut."""
    result = subprocess.run(
        ["python", "-m", "mutmut", "results"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def parse_results(output):
    """Parse mutmut results output."""
    stats = {
        "killed": 0,
        "survived": 0,
        "timeout": 0,
        "suspicious": 0,
        "total": 0,
    }

    survivors_by_module = defaultdict(list)

    for line in output.split("\n"):
        if not line.strip():
            continue

        # Match lines like: "1. killed hponas/space.py:45"
        match = re.match(r"(\d+)\.\s+(\w+)\s+([^:]+):(\d+)", line)
        if match:
            mut_id, status, filepath, lineno = match.groups()
            stats[status] = stats.get(status, 0) + 1
            stats["total"] += 1

            if status == "survived":
                # Extract module name from filepath
                module = filepath.replace("hponas/", "").replace(".py", "")
                survivors_by_module[module].append(int(mut_id))

    return stats, survivors_by_module


def main():
    print("Fetching mutation testing results...")
    output = get_mutation_results()

    stats, survivors = parse_results(output)

    print("\n" + "="*60)
    print("MUTATION TESTING RESULTS")
    print("="*60)

    print(f"\nTotal mutations: {stats['total']}")
    print(f"  Killed:    {stats['killed']}")
    print(f"  Survived:  {stats['survived']}")
    print(f"  Timeout:   {stats['timeout']}")
    print(f"  Suspicious: {stats.get('suspicious', 0)}")

    if stats['total'] > 0:
        kill_score = 100 * stats['killed'] / stats['total']
        print(f"\nKill Score: {stats['killed']}/{stats['total']} = {kill_score:.2f}%")

        # Compare to previous
        prev_killed = 1563
        prev_total = 1818
        prev_score = 85.97

        print(f"Previous:   {prev_killed}/{prev_total} = {prev_score:.2f}%")
        print(f"Change:     {stats['killed'] - prev_killed:+d} kills")
        print(f"            {stats['total'] - prev_total:+d} mutations")
        print(f"            {kill_score - prev_score:+.2f}%")

        # Gap to 90%
        target = 0.90 * stats['total']
        gap = int(target) - stats['killed']
        print(f"\nGap to 90%: {gap} more kills needed")

    if survivors:
        print("\n" + "="*60)
        print("SURVIVORS BY MODULE")
        print("="*60)

        sorted_modules = sorted(survivors.items(), key=lambda x: len(x[1]), reverse=True)
        for module, mut_ids in sorted_modules:
            count = len(mut_ids)
            pct = 100 * count / stats['survived'] if stats['survived'] > 0 else 0
            print(f"  {module:30s} {count:3d} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
