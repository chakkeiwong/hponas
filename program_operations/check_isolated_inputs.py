"""Execute the GAP test dependencies in the actual V03 input snapshot only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib

ROOT=Path('/home/ubuntu/workspace/hponas')
sys.path.insert(0,str(ROOT))


def bind(path):return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    if len(sys.argv)!=1:raise ValueError('No arguments accepted')
    from validation.v03_mutation_testing import prepare_mutation_workspace,test_data_inventory,same_test_data
    from tools.source_identity import source_digest
    out=Path(os.environ['HPONAS_OPERATION_DIRECTORY'])/'isolated-inputs'
    assert out.parent.parent==ROOT/'docs/program/operations-runs'
    out.mkdir(exist_ok=False)
    source=source_digest()
    work=prepare_mutation_workspace()
    assert source_digest(work)==source
    assert same_test_data(test_data_inventory(ROOT),test_data_inventory(work))
    # Source-root imports and checkout docs must not rescue missing inputs.
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    env['PYTHONPATH']=str(ROOT/'.hponas-runtime/spec-deps')
    command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        '--continue-on-collection-errors','tests/unit/test_gap_trace.py',
        'tests/unit/test_gap_installation_operations.py']
    began=time.monotonic()
    config=tomllib.loads((work/'pyproject.toml').read_text())['tool']['mutmut']
    collection=[sys.executable,'-m','pytest',*config['pytest_add_cli_args'],
                '-p','no:cacheprovider','--collect-only']
    with (out/'collection.log').open('x') as log:
        collected=subprocess.run(collection,cwd=work,env=env,stdout=log,
            stderr=subprocess.STDOUT,timeout=240)
    assert collected.returncode==0, 'Actual isolated collection failed; inspect collection.log'
    with (out/'tests.log').open('x') as log:
        result=subprocess.run(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,
            timeout=max(.1,240-(time.monotonic()-began)))
    passed=result.returncode==0 and source_digest()==source_digest(work)==source
    report=dict(kind='gap_isolated_input_verification_v1',passed=passed,
        source_digest=source,end_source_digest=source_digest(),workspace=str(work),
        command=command,returncode=result.returncode,elapsed_seconds=time.monotonic()-began,
        log=bind(out/'tests.log'),copied_input_inventory=test_data_inventory(work),
        collection=dict(command=collection,returncode=collected.returncode,log=bind(out/'collection.log')),
        scientific_acceptance=False,official_campaigns=0)
    with (out/'receipt.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(passed=passed,receipt=str(out/'receipt.json'))))
    return int(not passed)


if __name__=='__main__':raise SystemExit(main())
