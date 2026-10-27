#!/usr/bin/python3 -I
"""Fixed, bounded local development operations; never forwards caller commands."""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path('/home/ubuntu/workspace/hponas')
PYTHON = '/home/ubuntu/miniforge3/bin/python'
RUNS = ROOT / 'docs/program/operations-runs'
CHECKS = (
    ('tools/update_progress.py',),
    ('tools/update_progress.py', '--verify'),
    ('tools/check_program_sync.py',),
    ('tools/check_protocols.py',),
    ('tools/program_continuation.py',),
    ('docs/program/evidence/2026-10-04/execution-review-03/audit_program.py',),
)
TESTS = {
    'test-study': (
        'tests/unit/test_parallel_evaluation_controller.py',
        'tests/unit/test_parallel_execution_context.py',
        'tests/unit/test_generational_transfer.py',
        'tests/unit/test_population_checkpoint.py',
        'tests/unit/test_architecture_coordinates.py',
        'tests/integration/test_product_reporting.py',
        'tests/unit/test_ray_control_paths.py',
        'tests/unit/test_ray_streaming_accounting.py',
        'tests/unit/test_ray_cancellation_boundary.py',
        'tests/unit/test_rung_diagnostics.py',
        'tests/unit/test_capability_routing.py',
        'tests/integration/test_declared_evaluation.py',
        'tests/integration/test_declared_streaming.py',
        'tests/integration/test_streaming_scheduler.py',
        'tests/unit/test_streaming_reporting.py',
        'tests/unit/test_study_progress_controls.py',
        'tests/unit/test_explicit_evaluation_policy.py',
        'tests/integration/test_tpe_scheduler.py',
        'tests/unit/test_study_configuration_contract.py',
        'tests/unit/test_study_checkpoint_contract.py',
        'tests/unit/test_study_checkpoint_additional.py',
        'tests/unit/test_study_public_entrypoints.py',
        'tests/unit/test_study_terminal_contract.py',
        'tests/unit/test_study_batch_controls.py',
        'tests/unit/test_study_suggestion_termination.py',
        'tests/integration/test_multi_objective_study.py',
    ),
    'test-search': (
        'tests/test_pibo.py',
        'tests/test_repair_regressions.py',
        'tests/unit/test_uncovered_public_results.py',
        'tests/validation/test_tier1_finite.py',
        'tests/validation/test_tier1_evidence.py',
        'tests/validation/test_tier0_exposure.py',
        'tests/unit/test_space_coordinate_contract.py',
        'tests/test_contracts.py',
        'tests/test_searchers_tier0.py',
        'tests/validation/test_v03_phase_contract.py',
        'tests/validation/test_v03_equivalence.py',
        'tests/validation/test_v03_optional_fidelity_proof.py',
        'tests/validation/test_v03_raw_outcomes.py',
        'tests/validation/test_v03_resource_scheduler.py',
        'tests/validation/test_v03_test_order.py',
        'tests/validation/test_bank_nas.py',
        'tests/integration/test_bank_nas_workflow.py',
        'tests/validation/test_bank_decisions.py',
        'tests/integration/test_bank_decision_workflow.py',
        'tests/validation/test_bank_solvers.py',
        'tests/integration/test_bank_solver_workflow.py',
        'tests/validation/test_bank_inference.py',
        'tests/integration/test_bank_inference_workflow.py',
        'tests/validation/test_bank_causal.py',
        'tests/integration/test_bank_causal_workflow.py',
        'tests/validation/test_bank_prediction.py',
        'tests/integration/test_bank_prediction_workflow.py',
        'tests/unit/test_gp_joint_batch.py',
        'tests/unit/test_gp_batch_boundaries.py',
        'tests/unit/test_capability_routing.py',
        'tests/conformance/test_searcher_contract.py',
        'tests/unit/test_gp_finite_acquisition.py',
        'tests/unit/test_gp_dimension_prior.py',
        'tests/unit/test_modern_gp_runtime_contract.py',
        'tests/unit/test_legacy_adapter_contract.py',
        'tests/unit/test_prior_public_contract.py',
        'tests/unit/test_tpe_public_contract.py',
        'tests/unit/test_tpe_observation_boundaries.py',
        'tests/unit/test_cmaes_public_contract.py',
        'tests/unit/test_ranked_warm_history.py',
        'tests/integration/test_categorical_priorband.py',
        'tests/integration/test_product_priorband.py',
        'tests/integration/test_cost_searcher.py',
        'tests/integration/test_trust_searcher.py',
    ),
    'test-store': (
        'tests/test_operations.py',
        'tests/integration/test_product_reporting.py',
        'tests/unit/test_rung_diagnostics.py',
        'tests/conformance/test_store_recovery.py',
        'tests/unit/test_store_query_contract.py',
        'tests/unit/test_store_snapshot_contract.py',
        'tests/unit/test_atomic_snapshot_contract.py',
        'tests/unit/test_persistence_evaluation_artifacts.py',
    ),
    'test-schedulers': (
        'tests/conformance/test_scheduler_contract.py',
        'tests/unit/test_scheduler_report_contract.py',
        'tests/unit/test_scheduler_rung_progress.py',
        'tests/unit/test_scheduler_state.py',
    ),
}
OPERATIONS = ('status', 'checks', *TESTS, 'check-rules', 'test-operations')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest():
    spec = importlib.util.spec_from_file_location('hponas_source_identity', ROOT / 'tools/source_identity.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_digest(ROOT)


def parse_operation(args):
    if len(args) != 1 or args[0] not in OPERATIONS:
        raise ValueError('Pass exactly one fixed operation: ' + ', '.join(OPERATIONS))
    return args[0]


def commands(operation):
    if operation == 'checks':
        return [[PYTHON, *args] for args in CHECKS]
    if operation in TESTS:
        result = [[PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *TESTS[operation]]]
        if operation == 'test-search':
            # Retain every reviewed file, in order, under the existing 300s cap.
            # The growing single group reached its bound on 18 October 2026.
            roster = TESTS[operation]
            contract_boundary = roster.index('tests/validation/test_v03_phase_contract.py')
            boundary = roster.index('tests/unit/test_gp_joint_batch.py')
            result = [[PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *part]
                      for part in (roster[:contract_boundary], roster[contract_boundary:boundary], roster[boundary:])]
            result.insert(0, ['/usr/bin/python3', '-I', str(ROOT / 'program_operations/check_collection.py')])
            result.insert(1, ['/usr/bin/python3', '-I', str(ROOT / 'program_operations/check_proof_context.py')])
        mode = {'test-study':'ray','test-store':'postgres'}.get(operation)
        if mode:
            result.append([PYTHON,str(ROOT/'program_operations/local_services.py'),mode])
        if operation == 'test-study':
            result.append([PYTHON,str(ROOT/'program_operations/local_services.py'),'ray-repeated'])
        return result
    scripts = {'check-rules': 'check_approval_rules.py', 'test-operations': 'test_operations.py'}
    if operation in scripts:
        return [['/usr/bin/python3', '-I', str(ROOT / 'program_operations' / scripts[operation])]]
    raise ValueError('No process command for operation')


def environment():
    env = {key: os.environ[key] for key in ('HOME', 'USER', 'LOGNAME', 'LANG') if key in os.environ}
    env.update(PATH=str(ROOT / '.hponas-runtime/program-tools/bin') + ':/home/ubuntu/miniforge3/bin:/usr/bin:/bin',
               PYTHONPATH=str(ROOT / '.hponas-runtime/postgres-deps') + ':' + str(ROOT / '.hponas-runtime/spec-deps') + ':' + str(ROOT),
               PYTHONNOUSERSITE='1', PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1',
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', CUDA_VISIBLE_DEVICES='',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               NUMEXPR_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
    return env


def run_child(command, log, env, timeout=300):
    start = time.monotonic()
    timed_out = False
    with log.open('x') as output:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            child.wait(timeout=timeout)
        except BaseException as exc:
            timed_out = isinstance(exc, subprocess.TimeoutExpired)
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            # Retire remaining members even if the group leader already exited.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=3)
            if not timed_out:
                raise
    return {'command': command, 'returncode': child.returncode, 'timed_out': timed_out,
            'elapsed_seconds': time.monotonic() - start,
            'log': {'path': str(log.relative_to(ROOT)), 'sha256': digest(log)}}


def status():
    spec = importlib.util.spec_from_file_location('hponas_continuation', ROOT / 'tools/program_continuation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    program = json.loads((ROOT / 'docs/program/program.json').read_text())
    result = module.continuation(program)
    active = program.get('review_register', {}).get('active_campaign')
    observation = None
    if active and active.get('health_log'):
        directory = (ROOT / active['health_log']).resolve()
        if not directory.is_relative_to(ROOT / 'docs/program/evidence'):
            raise ValueError('Registered health directory escapes program evidence')
        spec = importlib.util.spec_from_file_location('hponas_run_status', ROOT / 'program_operations/run_status.py')
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        observation = reader.observe(directory)
    return {'revision': program['revision'], 'goal': program['goal'],
            'active_work_item': program['active_work_item'], 'next_step': result['next_step'],
            'continuation': result['status'], 'master_complete': result['master_complete'],
            'external_blockers': result['external_blockers'], 'source_digest': source_digest(),
            'work_items': len(program['work_items']), 'stages': len(program['continuation']['steps']),
            'requirements': len(program['requirements']),
            'registered_campaign_status': active.get('status') if active else None,
            'observed_execution': observation}


def execute(operation):
    RUNS.mkdir(parents=True, exist_ok=True)
    # Serialize operations; this lock is not a campaign admission mechanism.
    with (RUNS / '.operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + operation + '-' + uuid4().hex[:8]
        out = RUNS / name
        out.mkdir(exist_ok=False)
        before = source_digest()
        revision = json.loads((ROOT / 'docs/program/program.json').read_text())['revision']
        rows = []
        error = None
        try:
            for index, command in enumerate(commands(operation)):
                env = environment()
                env['HPONAS_OPERATION_DIRECTORY'] = str(out)
                row = run_child(command, out / f'check-{index:02d}.log', env)
                rows.append(row)
                if row['returncode'] or row['timed_out']:
                    break
        except BaseException as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        after = source_digest()
        passed = (error is None and len(rows) == len(commands(operation))
                  and all(row['returncode'] == 0 and not row['timed_out'] for row in rows)
                  and before == after)
        receipt = {'kind': 'fixed_local_operation_v1', 'operation': operation,
                   'revision': revision, 'source_digest': before, 'end_source_digest': after,
                   'helper_sha256': digest(__file__), 'passed': passed, 'error': error,
                   'limits': {'seconds_per_process': 300, 'cpu_count': 1, 'gpu': False},
                   'scientific_acceptance': False, 'checks': rows}
        with (out / 'receipt.json').open('x') as handle:
            json.dump(receipt, handle, indent=2)
            handle.write('\n')
        return {'passed': passed, 'revision': revision, 'operation': operation,
                'receipt': str((out / 'receipt.json').relative_to(ROOT)),
                'elapsed_seconds': sum(row['elapsed_seconds'] for row in rows), 'error': error}


def main():
    try:
        operation = parse_operation(sys.argv[1:])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result = status() if operation == 'status' else execute(operation)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if operation == 'status' or result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
