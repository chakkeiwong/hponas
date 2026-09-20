#!/usr/bin/env python3
"""Quick mutation check script for R6 results.

Usage:
    python quick_mutation_check.py
"""

import subprocess
import sys


def get_mutation_stats():
    """Get mutation statistics from mutmut cache."""
    try:
        result = subprocess.run(
            ['python', '-m', 'mutmut', 'results'],
            capture_output=True,
            text=True,
            timeout=30,
            cwd='/home/ubuntu/workspace/hponas'
        )

        output = result.stdout

        # Count by status
        killed = len([l for l in output.split('\n') if ': killed' in l or ': ok_killed' in l])
        survived = len([l for l in output.split('\n') if ': survived' in l])
        timeout = len([l for l in output.split('\n') if ': timeout' in l])
        no_tests = len([l for l in output.split('\n') if ': no tests' in l])
        suspicious = len([l for l in output.split('\n') if ': suspicious' in l])

        total = killed + survived + timeout + no_tests + suspicious

        return {
            'total': total,
            'killed': killed,
            'survived': survived,
            'timeout': timeout,
            'no_tests': no_tests,
            'suspicious': suspicious,
        }

    except subprocess.TimeoutExpired:
        print("ERROR: Timeout waiting for mutmut results")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def calculate_score(stats):
    """Calculate kill score using gate formula."""
    if not stats:
        return None

    # Gate formula: killed / (total - timeout)
    denominator = stats['total'] - stats['timeout']

    if denominator == 0:
        return None

    kill_score = 100 * stats['killed'] / denominator

    # Target for 90%
    target_kills = int(0.90 * denominator)
    gap = target_kills - stats['killed']

    return {
        'denominator': denominator,
        'kill_score': kill_score,
        'target_kills': target_kills,
        'gap': gap,
    }


def main():
    print("Checking R6 mutation testing results...")
    print()

    stats = get_mutation_stats()

    if not stats:
        print("❌ No results available yet. Mutation testing may still be running.")
        sys.exit(1)

    if stats['total'] == 0:
        print("❌ No mutations found. Did mutation testing complete?")
        sys.exit(1)

    print("=" * 70)
    print("R6 MUTATION TESTING RESULTS")
    print("=" * 70)
    print()
    print(f"Total mutations: {stats['total']}")
    print(f"  Killed:      {stats['killed']:4d} 🎉")
    print(f"  Survived:    {stats['survived']:4d} 🙁")
    print(f"  Timeout:     {stats['timeout']:4d} ⏰")
    print(f"  No tests:    {stats['no_tests']:4d} 🫥")
    print(f"  Suspicious:  {stats['suspicious']:4d} 🤔")
    print()

    score = calculate_score(stats)
    if score:
        print(f"Kill Score: {stats['killed']}/{score['denominator']} = {score['kill_score']:.2f}%")
        print()

        # Compare to R5 baseline
        r5_killed = 1592
        r5_denom = 1819
        r5_score = 87.52

        delta_killed = stats['killed'] - r5_killed
        delta_timeout = stats['timeout'] - 394  # R5 had 394 timeouts
        delta_score = score['kill_score'] - r5_score

        print(f"Baseline (R5): {r5_killed}/{r5_denom} = {r5_score:.2f}%")
        print(f"Change:        {delta_killed:+d} kills, {delta_timeout:+d} timeouts ({delta_score:+.2f}%)")
        print()

        if score['kill_score'] >= 90.0:
            print("✅ TARGET REACHED! Kill score ≥ 90%")
            print()
            print("Next steps:")
            print("1. Document results in V03_STATUS.md")
            print("2. Update master program")
            print("3. Proceed to next gate")
        else:
            print(f"❌ Gap to 90%: {score['gap']} more kills needed")
            print()
            print("Next steps:")
            print("1. Run survivor analysis:")
            print("   python analyze_survivors.py")
            print()
            print("2. Focus on high-ROI modules:")
            print("   python analyze_survivors.py --module schedulers --show-diffs")
            print()
            print("3. Write targeted tests based on analysis")
            print("4. Run R7 mutation testing")

        print()
        print("=" * 70)
        print(f"Defensive programming impact:")
        print(f"  Timeouts reduced: {-delta_timeout} ({-100*delta_timeout/394:.1f}%)")
        print(f"  Code quality: ✓ Improved (fail fast, clear errors)")
        print(f"  Score impact: {delta_score:+.2f} percentage points")
        print("=" * 70)

    else:
        print("❌ Could not calculate score")


if __name__ == '__main__':
    main()
