#!/usr/bin/python3 -I
"""Fixed bounded preparation actions; never allocates a scientific campaign."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-26/parallel-admission-02'
Q=BASE.parent/'parallel-qualification-run-02'
D=BASE.parent/'parallel-descendant-02'
A=BASE.parent/'parallel-final-audit-01'
sys.path[:0]=[str(ROOT),str(BASE)]
from program_operations import hponas_ops as ops
from tools.source_identity import source_digest

ACTIONS={
    'controls':[(Q/'run_controls.py',1250),(Q/'review_controller.py',300)],
    'review-admission':[(BASE/'review_repair.py',300),(BASE/'review_preparation.py',300)],
    'verify-calibration':[(BASE/'verify_calibration.py',300)],
    'prepare-descendant':[(D/'prepare.py',300)],
    'run-descendant':[(D/'run.py',1680)],
    'verify-descendant':[(D/'verify.py',300)],
    'reconstruct-admission':[(Q/'prerequisites.py',300)],
    'audit-preflight':[(A/'preflight_audit.py',1900)],
    'audit-review':[(A/'review_audit.py',600)],
    'review-service':[(BASE/'service-controls.py',300),(BASE/'review_service.py',300)],
}

def bind(path):return dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def read(path):return json.loads(path.read_text())
def write(path,value):
    with path.open('x') as handle:
        json.dump(value,handle,indent=2);handle.write('\n');handle.flush();os.fsync(handle.fileno())

def main():
    if len(sys.argv)!=2 or sys.argv[1] not in ACTIONS:raise ValueError('One fixed preparation operation required')
    operation=sys.argv[1]
    manifest_path=BASE/'operation-manifests'/(operation+'.json')
    manifest=read(manifest_path)
    if manifest['runner']!=bind(Path(__file__)) or manifest['source_digest']!=source_digest():
        raise ValueError('Reviewed runner and current source required')
    for ref in manifest['inputs']:
        if bind(ROOT/ref['path'])!=ref:raise ValueError('Preparation input changed: '+ref['path'])
    program=read(ROOT/'docs/program/program.json')
    stages={s['id']:s for s in program['continuation']['steps']}
    if program['active_work_item']!='PAR-QUAL-01' or stages['PAR-QUAL-01/PREPARE']['state']!='in_progress':
        raise ValueError('PAR-QUAL-01/PREPARE must be active')
    out=BASE/('operation-'+operation);out.mkdir(exist_ok=False)
    write(out/'allocation.json',dict(operation=operation,manifest=bind(manifest_path),
        source_digest=source_digest(),steps=[dict(script=bind(p),wall_seconds=t) for p,t in ACTIONS[operation]],
        scientific_campaigns=0,automatic_retry=False))
    env=dict(os.environ,**manifest['environment'])
    cpus=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,set(cpus[:24] if operation=='run-descendant' else cpus[:1]))
    rows=[];error=None;started=time.monotonic()
    try:
        for path,limit in ACTIONS[operation]:
            result=ops.run_child([ops.PYTHON,str(path)],out/(path.stem+'.log'),env,limit)
            rows.append(dict(script=bind(path),**result))
            write(out/(path.stem+'.json'),rows[-1])
            if result['returncode'] or result['timed_out']:raise ValueError('Fixed preparation failed: '+path.name)
        if source_digest()!=manifest['source_digest']:raise ValueError('Scientific source changed')
        for ref in manifest['inputs']:
            if bind(ROOT/ref['path'])!=ref:raise ValueError('Preparation source changed')
    except BaseException as exc:error=type(exc).__name__+': '+str(exc)
    write(out/'receipt.json',dict(passed=error is None,error=error,operation=operation,steps=rows,
        elapsed_seconds=time.monotonic()-started,source_digest=source_digest(),scientific_acceptance=False))
    print(json.dumps(dict(passed=error is None,error=error,operation=operation,receipt=bind(out/'receipt.json'))))
    return int(error is not None)

if __name__=='__main__':raise SystemExit(main())
