#!/usr/bin/python3 -I
"""Run one reviewed exact leaking-mutant control on the repaired source."""
import json
import os
from pathlib import Path
import signal
import sys
ROOT=Path('/home/ubuntu/workspace/hponas')
P=ROOT/'docs/program/evidence/2026-10-26/parallel-admission-03'
D=P.parent/'parallel-descendant-03'
sys.path[:0]=[str(ROOT),str(P)]
from preparation import bind,read,verify_binding
from tools.source_identity import source_digest
from program_operations import hponas_ops as ops

def main():
    if len(sys.argv)!=1:raise ValueError('No arguments accepted')
    assert hasattr(signal,'pidfd_send_signal') and hasattr(os,'pidfd_open')
    manifest=read(P/'descendant-launch-manifest.json')
    assert manifest['runner']==bind(Path(__file__)) and manifest['source_digest']==source_digest()
    for ref in manifest['inputs']:verify_binding(ref)
    program=read(ROOT/'docs/program/program.json')
    stages={r['id']:r for r in program['continuation']['steps']}
    assert program['active_work_item']=='PAR-QUAL-01'
    assert stages['PAR-QUAL-01/EXECUTE']['state']=='in_progress'
    assert not program['review_register']['source_frozen_by_active_run']
    target=D/'target-01'
    assert not (target/'guarded-execution').exists() and not (target/'result.json').exists()
    allocation=read(target/'allocation.json')
    assert allocation['source_digest']==source_digest() and 0<allocation['outer_wall_seconds']<=1650
    out=P/'operation-run-descendant';out.mkdir(exist_ok=False)
    def write(name,value):
        with (out/name).open('x') as handle:
            json.dump(value,handle,indent=2);handle.flush();os.fsync(handle.fileno())
    write('allocation.json',dict(manifest=bind(P/'descendant-launch-manifest.json'),
        target=bind(target/'allocation.json'),source_digest=source_digest(),automatic_retry=False))
    env=dict(os.environ,**read(P/'operation-environment.json'))
    result=ops.run_child(['/usr/bin/python3',str(D/'run.py')],out/'run.log',env,allocation['outer_wall_seconds']+30)
    passed=result['returncode']==0 and not result['timed_out']
    passed=passed and source_digest()==manifest['source_digest']
    for ref in manifest['inputs']:verify_binding(ref)
    write('receipt.json',dict(passed=passed,process=result,source_digest=source_digest(),
        scientific_campaigns=0,scientific_acceptance=False))
    print(json.dumps(dict(passed=passed,receipt=bind(out/'receipt.json'))),flush=True)
    return int(not passed)

if __name__=='__main__':raise SystemExit(main())
