"""Fixed no-training verification and audit for the five-state extension."""
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT/'extensions/rl-lqr5'
BASE = ROOT/'docs/program/evidence/2026-10-27/rl-lqr-02'
CORE = 'fb5a83647bd5d73aaff21e360bab73432c670c6b08038e52507749a7de99e320'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def require(value, message):
    if not value:
        raise ValueError(message)


def verify_runtime():
    lock = read(ROOT/'extensions/rl-lqr/runtime-lock.json')
    for name, version in lock['versions'].items():
        require(importlib.metadata.version(name) == version, 'Runtime version changed: '+name)
    for name, digest in lock['files'].items():
        require(hashlib.sha256((ROOT/lock['overlay']/name).read_bytes()).hexdigest() == digest,
                'Runtime overlay changed: '+name)


def verify_report(report):
    from hponas_rl_lqr5.reference import oracle_report
    from hponas_rl_lqr5.search import capability_report
    require(report['oracle'] == oracle_report(), 'Oracle result differs')
    require(report['capability'] == capability_report(), 'Capability result differs')
    require(report['training_transitions'] == 0, 'Unexpected training allocation')
    require(report['scope'] == 'five_state_formulation_and_network_preflight_only', 'Unsupported scope')


def preflight(out):
    tests = [EXT/'tests'/name for name in ('test_reference.py', 'test_search.py', 'test_catalog.py')]
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        '--junitxml='+str(out/'tests.xml'), *map(str, tests)], check=True, timeout=240)
    suites = list(ET.parse(out/'tests.xml').getroot().iter('testsuite'))
    require(suites and all(int(s.get('skipped', 0)) == 0 for s in suites), 'Skipped tests')
    from hponas_rl_lqr5.reference import oracle_report
    from hponas_rl_lqr5.search import capability_report, search_space
    report = {'oracle': oracle_report(), 'capability': capability_report(), 'search_space': search_space().to_dict(),
              'tests': sum(int(s.get('tests', 0)) for s in suites), 'training_transitions': 0,
              'scope': 'five_state_formulation_and_network_preflight_only'}
    verify_report(report); write(out/'preflight-result.json', report)
    print(json.dumps(report, indent=2))


def audit(out):
    program = read(ROOT/'docs/program/program.json')
    evidence = {e['id']: e for e in program['evidence']}
    ref = evidence['E-RL-LQR02-PREFLIGHT-RESULT']; report_path = ROOT/ref['path']
    require(hashlib.sha256(report_path.read_bytes()).hexdigest() == ref['sha256'], 'Result binding differs')
    report = read(report_path); verify_report(report)
    receipt = read(report_path.parent/'receipt.json')
    require(receipt['passed'] and receipt['training_transitions'] == 0, 'Preflight receipt failed')
    manifest = read(report_path.parent/'manifest.json')
    for b in [manifest['runner'], *manifest['inputs']]:
        require(hashlib.sha256((ROOT/b['path']).read_bytes()).hexdigest() == b['sha256'], 'Current input differs')
        require(hashlib.sha256((report_path.parent/'inputs'/b['path']).read_bytes()).hexdigest() == b['sha256'], 'Archived input differs')
    rejected = []
    for name in ('false_optimum', 'false_bgpbt_support', 'false_training'):
        bad = deepcopy(report)
        if name == 'false_optimum': bad['oracle']['optimal_cost'] = 0.
        elif name == 'false_bgpbt_support': bad['capability']['current_local_bgpbt_sac_supported'] = True
        else: bad['training_transitions'] = 512
        try: verify_report(bad)
        except ValueError: rejected.append(name)
    require(len(rejected) == 3, 'False evidence accepted')
    result = {'passed': True, 'tests': report['tests'], 'oracle': report['oracle'],
              'bgpbt_sac_supported': False, 'training_transitions': 0, 'negative_controls': rejected,
              'source_closure_files': len(manifest['inputs'])+1,
              'scope': report['scope']}
    write(out/'audit-result.json', result); print(json.dumps(result, indent=2))


def master_audit(out):
    from tools.source_identity import source_digest
    from tools.gap_trace import validate
    from tools.program_continuation import continuation
    program = read(ROOT/'docs/program/program.json')
    require(source_digest(ROOT) == CORE, 'Accepted core changed')
    evidence = {e['id']: e for e in program['evidence']}
    entry = evidence['E-RL-LQR02-AUDIT-RESULT']; path = ROOT/entry['path']
    require(hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], 'Audit binding differs')
    outcome = read(path)
    require(outcome['passed'] and outcome['bgpbt_sac_supported'] is False, 'Audit scope differs')
    candidate = deepcopy(program)
    for step in candidate['continuation']['steps']:
        if step['id'] == 'GAP-01/FINAL-AUDIT': step['state'] = 'complete'
        require(step['state'] == 'complete', 'Incomplete stage: '+step['id'])
    for work in candidate['work_items']:
        if work['id'] == 'GAP-01': work['state'] = 'complete'
        require(work['state'] == 'complete', 'Incomplete work: '+work['id'])
    candidate['active_work_item'] = None
    validate(read(ROOT/'docs/program/gap_closure.json'), candidate, ROOT, final=True)
    require(continuation(candidate)['master_complete'], 'Candidate master incomplete')
    bad = deepcopy(candidate)
    next(s for s in bad['continuation']['steps'] if s['id'] == 'RL-LQR-02/PREFLIGHT')['state'] = 'planned'
    try: continuation(bad)
    except ValueError as exc: require('predecessor is incomplete' in str(exc), 'Unexpected refusal')
    else: raise ValueError('Incomplete preflight falsely accepted')
    result = {'passed': True, 'core_source': CORE, 'work_items': len(candidate['work_items']),
        'stages': len(candidate['continuation']['steps']), 'requirements': len(candidate['requirements']),
        'original_gap_trace_valid': True, 'incomplete_preflight_refused': True,
        'training_transitions': 0, 'bgpbt_sac_supported': False,
        'scope': 'Original finite master plus five-state definition/readiness; no BG-PBT/SAC execution claim'}
    write(out/'master-audit-result.json', result); print(json.dumps(result, indent=2))


def main():
    require(len(sys.argv) == 3, 'Fixed operation and owned output required')
    op, out = sys.argv[1], Path(sys.argv[2])
    require(out.resolve().is_relative_to(BASE) and out.is_dir(), 'Output escapes owned directory')
    verify_runtime()
    operations = {'preflight': preflight, 'audit': audit, 'master-audit': master_audit}
    require(op in operations, 'Unknown operation')
    operations[op](out)


if __name__ == '__main__':
    main()
