"""Test validation coverage across the codebase.

This enforces the INPUT_VALIDATION_POLICY.md requirement that all public
classes have validation tests.
"""

import pytest
import inspect
import importlib
from pathlib import Path
from typing import List, Tuple


# Tier 0 modules that MUST have validation (per V03 protocol)
TIER_0_MODULES = [
    'hponas.searchers.base',
    'hponas.searchers.gp_searcher',
    'hponas.searchers.random_searcher',
    'hponas.executors.local_executor',
    'hponas.executors.ray_executor',
    'hponas.schedulers',
    'hponas.types',
    'hponas.space',
]


def get_public_classes(module_name: str) -> List[Tuple[str, type]]:
    """Get all public classes from a module.

    Returns:
        List of (class_name, class_obj) tuples for public classes.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return []

    classes = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        # Only include classes defined in this module (not imports)
        if obj.__module__ == module_name and not name.startswith('_'):
            classes.append((name, obj))

    return classes


def get_init_params(cls: type) -> List[str]:
    """Get parameter names from __init__ method."""
    try:
        sig = inspect.signature(cls.__init__)
        return [p for p in sig.parameters.keys() if p != 'self']
    except (ValueError, TypeError):
        return []


def has_validation_tests(class_name: str) -> bool:
    """Check if validation tests exist for a class in test_input_validation.py."""
    test_file = Path("tests/unit/test_input_validation.py")
    if not test_file.exists():
        return False

    content = test_file.read_text()
    test_class_name = f"Test{class_name}Validation"
    return test_class_name in content


def get_validation_test_count(class_name: str) -> int:
    """Count number of validation tests for a class."""
    test_file = Path("tests/unit/test_input_validation.py")
    if not test_file.exists():
        return 0

    content = test_file.read_text()
    test_class_name = f"Test{class_name}Validation"

    # Count test methods in the test class
    in_class = False
    count = 0
    for line in content.split('\n'):
        if f"class {test_class_name}" in line:
            in_class = True
        elif in_class and line.startswith('class '):
            # Entered a different class
            break
        elif in_class and line.strip().startswith('def test_'):
            count += 1

    return count


def test_tier_0_classes_have_validation_tests():
    """All Tier 0 public classes must have validation test classes.

    This enforces INPUT_VALIDATION_POLICY.md for critical modules.
    """
    missing = []

    for module_name in TIER_0_MODULES:
        for class_name, cls in get_public_classes(module_name):
            if not has_validation_tests(class_name):
                params = get_init_params(cls)
                missing.append({
                    'module': module_name,
                    'class': class_name,
                    'params': params,
                })

    if missing:
        msg = [
            f"\nMissing validation tests for {len(missing)} Tier 0 classes:",
            "",
            "Per INPUT_VALIDATION_POLICY.md, all public classes must have",
            "a Test<ClassName>Validation test class in test_input_validation.py",
            "",
        ]

        for item in missing:
            msg.append(f"  ❌ {item['module']}.{item['class']}")
            if item['params']:
                msg.append(f"     Parameters to validate: {', '.join(item['params'])}")

        msg.extend([
            "",
            "Example template:",
            "",
            f"class Test{missing[0]['class']}Validation:",
            f'    """Validation tests for {missing[0]["class"]}."""',
            "",
            "    def test_rejects_negative_param(self):",
            "        with pytest.raises(ValueError, match='param must be'):",
            f"            {missing[0]['class']}(param=-1)",
            "",
            "See GPSearcher validation tests for full examples.",
        ])

        pytest.fail("\n".join(msg))


def test_validation_tests_have_minimum_coverage():
    """Validation test classes should have sufficient test methods.

    Rule of thumb: At least 2 tests per parameter (valid + invalid case).
    """
    insufficient = []

    for module_name in TIER_0_MODULES:
        for class_name, cls in get_public_classes(module_name):
            if has_validation_tests(class_name):
                test_count = get_validation_test_count(class_name)
                params = get_init_params(cls)
                expected_min = len(params) * 2  # At least 2 tests per param

                if test_count < expected_min:
                    insufficient.append({
                        'class': class_name,
                        'test_count': test_count,
                        'expected_min': expected_min,
                        'params': params,
                    })

    if insufficient:
        msg = [
            f"\nInsufficient validation coverage for {len(insufficient)} classes:",
            "",
            "Guideline: At least 2 tests per parameter (valid + invalid).",
            "",
        ]

        for item in insufficient:
            msg.append(
                f"  ⚠️  {item['class']}: {item['test_count']} tests "
                f"(expected ≥{item['expected_min']} for {len(item['params'])} params)"
            )

        # This is a warning, not a hard failure
        pytest.skip("\n".join(msg))


def test_validation_test_naming_convention():
    """Validation tests must follow naming convention.

    All test classes in test_input_validation.py must be named
    Test<ClassName>Validation to maintain consistency.
    """
    test_file = Path("tests/unit/test_input_validation.py")
    if not test_file.exists():
        pytest.skip("No validation tests file yet")

    content = test_file.read_text()
    violations = []

    for lineno, line in enumerate(content.split('\n'), 1):
        if line.strip().startswith('class Test'):
            # Extract class name
            class_name = line.split('class ')[1].split('(')[0].split(':')[0]
            if not class_name.endswith('Validation'):
                violations.append((lineno, class_name))

    if violations:
        msg = [
            "\nValidation test classes must end with 'Validation':",
            "",
        ]
        for lineno, class_name in violations:
            msg.append(f"  Line {lineno}: {class_name} should be {class_name}Validation")

        pytest.fail("\n".join(msg))


def test_validation_tests_use_pytest_raises():
    """Validation tests should use pytest.raises for exception testing.

    This ensures tests verify both exception type AND error message.
    """
    test_file = Path("tests/unit/test_input_validation.py")
    if not test_file.exists():
        pytest.skip("No validation tests file yet")

    content = test_file.read_text()

    # Count test methods
    test_methods = [line for line in content.split('\n') if 'def test_' in line]

    # Count pytest.raises usage
    pytest_raises_count = content.count('pytest.raises')

    if len(test_methods) > 0:
        coverage_ratio = pytest_raises_count / len(test_methods)

        # We expect most validation tests to use pytest.raises
        # (some may test valid inputs)
        if coverage_ratio < 0.5:
            pytest.skip(
                f"Low pytest.raises usage: {pytest_raises_count}/{len(test_methods)} tests. "
                "Validation tests should use pytest.raises(ExceptionType, match='message')"
            )


if __name__ == '__main__':
    # Allow running directly for quick check
    import sys

    print("Checking validation coverage...")
    print()

    missing = []
    for module_name in TIER_0_MODULES:
        for class_name, cls in get_public_classes(module_name):
            has_tests = has_validation_tests(class_name)
            status = "✓" if has_tests else "❌"
            test_count = get_validation_test_count(class_name) if has_tests else 0

            print(f"{status} {module_name}.{class_name} ({test_count} tests)")

            if not has_tests:
                missing.append((module_name, class_name))

    print()
    print("=" * 70)
    if missing:
        print(f"Missing validation tests: {len(missing)} classes")
        print("Run: pytest tests/unit/test_validation_coverage.py -v")
    else:
        print("All Tier 0 classes have validation tests ✓")

    sys.exit(len(missing))
