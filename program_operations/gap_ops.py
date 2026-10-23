#!/usr/bin/python3 -I
"""Fixed GAP-01 operations. No arbitrary command, destination or campaign CLI."""
import importlib.util
import json
from pathlib import Path
import sys

BASE = Path('/home/ubuntu/workspace/hponas/program_operations')
spec = importlib.util.spec_from_file_location('fixed_hponas_operations', BASE/'hponas_ops.py')
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)

# Extend only after reviewing new tests. These are development rosters, not
# scientific acceptance; exact command identities remain stable across phases.
TESTS = {
    'test-mo': ('tests/unit/test_multi_objective_joint_batch.py',
                'tests/integration/test_multi_objective_batch_recovery.py',
                'tests/integration/test_multi_objective_study.py', 'tests/unit/test_multi_objective_contract.py'),
    'test-evaluation': ('tests/integration/test_declared_evaluation.py', 'tests/unit/test_capability_routing.py',
                        'tests/integration/test_declared_streaming.py',
                        'tests/unit/test_explicit_evaluation_policy.py', 'tests/integration/test_tpe_scheduler.py',
                        'tests/unit/test_tpe_public_contract.py', 'tests/unit/test_recovery_refusal_boundaries.py',
                        'tests/unit/test_study_checkpoint_contract.py', 'tests/unit/test_study_public_entrypoints.py',
                        'tests/validation/test_v03_phase_contract.py'),
    'test-population': ('tests/unit/test_population_checkpoint.py', 'tests/unit/test_generational_transfer.py',
                        'tests/integration/test_population_adapter.py'),
    'test-local-ops': ('tests/test_operations.py', 'tests/unit/test_store_snapshot_contract.py',
                       'tests/test_local_service.py', 'tests/test_backup_security.py',
                       'tests/test_local_service_capacity.py', 'tests/validation/test_v03_phase_contract.py'),
    'test-transfer': ('tests/unit/test_ranked_warm_history.py', 'tests/unit/test_rgpe.py',
                      'tests/integration/test_declared_rgpe.py', 'tests/validation/test_v03_phase_contract.py'),
    'test-adapters': ('tests/integration/test_bank_prediction_workflow.py',
                      'tests/integration/test_bank_solver_workflow.py',
                      'tests/integration/test_caller_model_workflows.py',
                      'tests/unit/test_gap_installation_operations.py',
                      'tests/validation/test_v03_phase_contract.py'),
}
OPERATIONS = ('check-plan', 'check-rules', 'test-boundaries', *TESTS, 'audit-closure')


def parse(args):
    if len(args) != 1 or args[0] not in OPERATIONS:
        raise ValueError('Pass exactly one fixed GAP operation: '+', '.join(OPERATIONS))
    return args[0]


def commands(operation):
    if operation in TESTS:
        result = [[ops.PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *TESTS[operation]]]
        if operation == 'test-adapters':
            result.append([ops.PYTHON, str(BASE/'verify_gap_installation.py')])
        return result
    if operation in ('check-plan', 'audit-closure'):
        return [['/usr/bin/python3', '-I', str(BASE/'gap_audit.py'),
                 'plan' if operation == 'check-plan' else 'final']]
    if operation == 'test-boundaries':
        return [['/usr/bin/python3','-I',str(BASE/'test_gap_operations.py')],
                [ops.PYTHON,'-m','pytest','-q','-p','no:cacheprovider','tests/unit/test_gap_trace.py'],
                [ops.PYTHON,str(BASE/'check_isolated_inputs.py')]]
    scripts = {'check-rules':'check_gap_rules.py','test-boundaries':'test_gap_operations.py'}
    if operation in scripts:
        return [['/usr/bin/python3','-I',str(BASE/scripts[operation])]]
    raise ValueError('Unknown fixed operation')


def main():
    try:
        operation = parse(sys.argv[1:])
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    # Use the existing serialized, source-bound, one-CPU timeout/receipt engine.
    ops.commands = commands
    result = ops.execute(operation)
    receipt_path = ops.ROOT/result['receipt']
    receipt = json.loads(receipt_path.read_text())
    receipt['gap_runner_sha256'] = ops.digest(__file__)
    receipt['gap_manifest_sha256'] = ops.digest(ops.ROOT/'docs/program/gap_closure.json')
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
