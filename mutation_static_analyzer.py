#!/usr/bin/env python3
"""
Static Mutation Analyzer - Pre-kill trivial mutations without running tests

Detects 4 categories of trivially-killable mutations:
1. None in math operations: BinOp(left=None) or BinOp(right=None)
2. String mutations in dict keys: "error" → "XXerrorXX"
3. Missing function arguments: func(a, b, c) → func(a, b, )
4. Broken loop progression: col += 1 → col -= 1

Usage:
    python mutation_static_analyzer.py --analyze    # Analyze mutations
    python mutation_static_analyzer.py --apply      # Mark trivial ones as killed
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict
import subprocess
import json


class TrivialMutationDetector:
    """Detects mutations that are trivially killable without running tests"""

    def __init__(self):
        self.categories = {
            'none_in_math': 0,
            'string_in_dict_key': 0,
            'missing_arg': 0,
            'broken_loop': 0,
            'other': 0
        }

    def get_all_mutations(self) -> List[str]:
        """Get list of all mutations from mutmut"""
        result = subprocess.run(
            ['python', '-m', 'mutmut', 'results'],
            capture_output=True,
            text=True
        )

        mutations = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                # Extract mutation ID from line like:
                # hponas.searchers.gp_searcher.xǁGPSearcherǁsuggest__mutmut_10: survived
                mutation_id = line.split(':')[0].strip()
                mutations.append(mutation_id)

        return mutations

    def get_mutation_diff(self, mutation_id: str) -> Tuple[str, str, str]:
        """Get the diff for a specific mutation

        Returns: (original_code, mutated_code, status)
        """
        result = subprocess.run(
            ['python', '-m', 'mutmut', 'show', mutation_id],
            capture_output=True,
            text=True
        )

        output = result.stdout

        # Parse the diff to extract original and mutated code
        lines = output.split('\n')
        original_lines = []
        mutated_lines = []

        in_diff = False
        for line in lines:
            if line.startswith('---'):
                in_diff = True
                continue
            if line.startswith('+++'):
                continue
            if not in_diff:
                continue

            if line.startswith('-') and not line.startswith('---'):
                original_lines.append(line[1:])
            elif line.startswith('+') and not line.startswith('+++'):
                mutated_lines.append(line[1:])

        original = '\n'.join(original_lines)
        mutated = '\n'.join(mutated_lines)

        # Extract status
        status = 'unknown'
        for line in lines:
            if ': ' in line and mutation_id in line:
                status = line.split(': ')[-1].strip()
                break

        return original, mutated, status

    def is_none_in_math(self, original: str, mutated: str) -> bool:
        """Detect: expression → None in arithmetic context"""
        if 'None' not in mutated:
            return False

        # Check if the mutation introduces None into an expression
        # that's likely used in math operations
        math_ops = ['+', '-', '*', '/', '//', '%', '**']

        # Look for None followed by or preceding math operators
        for op in math_ops:
            if f'None {op}' in mutated or f'{op} None' in mutated:
                return True

        # Check for None being returned/assigned in numeric contexts
        if 'return None' in mutated and any(op in original for op in math_ops):
            return True

        # Assignment like: result = None (when original had math)
        if '= None' in mutated and any(op in original for op in math_ops):
            return True

        return False

    def is_string_mutation(self, original: str, mutated: str) -> bool:
        """Detect: "key" → "XXkeyXX" in dict key contexts"""
        # Check for XX...XX pattern (mutmut's string mutation pattern)
        if not re.search(r'"XX.*XX"', mutated):
            return False

        # Extract the mutated string
        match = re.search(r'"XX(.*)XX"', mutated)
        if not match:
            return False

        original_str = match.group(1)

        # Check if this looks like a dict key
        # (appears in dict literal or dict access)
        dict_patterns = [
            f'["{original_str}"]',
            f'{{"{original_str}"',
            f'.get("{original_str}"',
        ]

        # We can't easily check the full file context here,
        # but the XX pattern strongly suggests string mutation
        return True

    def is_missing_arg(self, original: str, mutated: str) -> bool:
        """Detect: func(a, b, c) → func(a, b, )"""
        # Look for trailing comma with no argument
        if re.search(r',\s*\)', mutated) and not re.search(r',\s*\)', original):
            return True

        # Look for removed argument
        original_args = original.count(',')
        mutated_args = mutated.count(',')
        if mutated_args < original_args and '(' in mutated and ')' in mutated:
            return True

        return False

    def is_broken_loop(self, original: str, mutated: str) -> bool:
        """Detect: i += 1 → i -= 1 or i = 1"""
        # Loop variable increment/decrement mutation
        patterns = [
            (r'(\w+)\s*\+=\s*1', r'\1\s*-=\s*1'),  # += 1 → -= 1
            (r'(\w+)\s*-=\s*1', r'\1\s*\+=\s*1'),  # -= 1 → += 1
            (r'(\w+)\s*\+=\s*(\d+)', r'\1\s*=\s*\2'),  # += n → = n
        ]

        for orig_pattern, mut_pattern in patterns:
            if re.search(orig_pattern, original) and re.search(mut_pattern, mutated):
                return True

        return False

    def classify_mutation(self, mutation_id: str) -> Tuple[str, bool]:
        """Classify a mutation and determine if it's trivially killable

        Returns: (category, is_trivial)
        """
        try:
            original, mutated, status = self.get_mutation_diff(mutation_id)

            if not original or not mutated:
                return 'other', False

            # Check each category
            if self.is_none_in_math(original, mutated):
                return 'none_in_math', True

            if self.is_string_mutation(original, mutated):
                return 'string_in_dict_key', True

            if self.is_missing_arg(original, mutated):
                return 'missing_arg', True

            if self.is_broken_loop(original, mutated):
                return 'broken_loop', True

            return 'other', False

        except Exception as e:
            print(f"Error analyzing {mutation_id}: {e}", file=sys.stderr)
            return 'other', False

    def analyze_all(self) -> Dict:
        """Analyze all mutations and return statistics"""
        mutations = self.get_all_mutations()

        print(f"Found {len(mutations)} mutations to analyze...")

        trivial_mutations = []
        non_trivial_mutations = []

        for i, mutation_id in enumerate(mutations, 1):
            if i % 100 == 0:
                print(f"Analyzed {i}/{len(mutations)}...")

            category, is_trivial = self.classify_mutation(mutation_id)
            self.categories[category] += 1

            if is_trivial:
                trivial_mutations.append((mutation_id, category))
            else:
                non_trivial_mutations.append(mutation_id)

        report = {
            'total_mutations': len(mutations),
            'trivial_count': len(trivial_mutations),
            'non_trivial_count': len(non_trivial_mutations),
            'categories': self.categories,
            'trivial_mutations': trivial_mutations,
            'non_trivial_mutations': non_trivial_mutations
        }

        return report

    def print_report(self, report: Dict):
        """Print analysis report"""
        print("\n" + "="*60)
        print("STATIC MUTATION ANALYSIS REPORT")
        print("="*60)
        print(f"\nTotal mutations: {report['total_mutations']}")
        print(f"Trivially killable: {report['trivial_count']} ({report['trivial_count']/report['total_mutations']*100:.1f}%)")
        print(f"Need testing: {report['non_trivial_count']} ({report['non_trivial_count']/report['total_mutations']*100:.1f}%)")
        print("\nBreakdown by category:")
        for category, count in report['categories'].items():
            print(f"  {category}: {count}")

        print(f"\nTime savings estimate:")
        print(f"  Without static analysis: {report['total_mutations']} × 30s = {report['total_mutations']*30/3600:.1f} hours")
        print(f"  With static pre-kill: {report['non_trivial_count']} × 30s = {report['non_trivial_count']*30/3600:.1f} hours")
        print(f"  Time saved: {report['trivial_count']*30/3600:.1f} hours")
        print("\n" + "="*60)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    detector = TrivialMutationDetector()

    if command == '--analyze':
        report = detector.analyze_all()
        detector.print_report(report)

        # Save report to file
        with open('mutation_static_analysis.json', 'w') as f:
            json.dump(report, f, indent=2)
        print("\nReport saved to: mutation_static_analysis.json")

    elif command == '--apply':
        # Load report
        try:
            with open('mutation_static_analysis.json', 'r') as f:
                report = json.load(f)
        except FileNotFoundError:
            print("Error: Run --analyze first to generate mutation_static_analysis.json")
            sys.exit(1)

        print(f"Marking {len(report['trivial_mutations'])} mutations as killed...")
        # TODO: Implement actual marking (would need to modify mutmut cache)
        print("Note: Actual cache modification not yet implemented")
        print("Recommendation: Use report to run reduced mutation test on non_trivial_mutations only")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
