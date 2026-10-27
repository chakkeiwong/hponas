#!/usr/bin/python3 -I
"""Correct the preflight interpreter; execute the original target exactly once."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
ROOT=Path('/home/ubuntu/workspace/hponas')
P=ROOT/'docs/program/evidence/2026-10-26/parallel-admission-02'
D=P.parent/'parallel-descendant-02'
sys.path[:0]=[str(ROOT),str(P)]
from preparation import bind,read
from tools.source_identity import source_digest
from program_operations import hponas_ops as ops

def main():
    if len(sys.argv)!=1:raise ValueError('No arguments accepted')
    assert hasattr(signal,'pidfd_send_signal') and hasattr(os,'pidfd_open')
    manifest=read(P/'descendant-launch-v2-manifest.json')
    assert manifest['runner']==bind(Path(__file__)) and manifest['source_digest']==source_digest()
    for ref in manifest['inputs']:assert bind(ROOT/ref['path'])==ref,ref['path']
    previous=read(P/'operation-run-descendant/receipt.json')
    assert not previous['passed'] and previous['steps'][0]['returncode']==1
    assert 'hasattr(signal' in (P/'operation-run-descendant/run.log').read_text()
    target=D/'target-01'
    assert not (target/'guarded-execution').exists() and not (target/'result.json').exists()
    out=P/'operation-run-descendant-02';out.mkdir(exist_ok=False)
    def write(name,value):
        with (out/name).open('x') as handle:
            json.dump(value,handle,indent=2);handle.flush();os.fsync(handle.fileno())
    write('allocation.json',dict(manifest=bind(P/'descendant-launch-v2-manifest.json'),
        target=bind(target/'allocation.json'),source_digest=source_digest(),automatic_retry=False))
    env=dict(os.environ,**read(P/'operation-environment.json'))
    command=['/usr/bin/python3',str(D/'run.py')]
    result=ops.run_child(command,out/'run.log',env,read(target/'allocation.json')['outer_wall_seconds']+30)
    passed=result['returncode']==0 and not result['timed_out']
    write('receipt.json',dict(passed=passed,process=result,source_digest=source_digest(),
        scientific_campaigns=0,scientific_acceptance=False))
    print(json.dumps(dict(passed=passed,receipt=bind(out/'receipt.json'))),flush=True)
    return int(not passed)

if __name__=='__main__':raise SystemExit(main())
