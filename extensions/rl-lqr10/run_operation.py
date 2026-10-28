"""Fixed stage entry points. All runtime and resources are runner-owned."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
EXT=ROOT/'extensions/rl-lqr10'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-04'

def main():
    op,out=sys.argv[1],Path(sys.argv[2])
    if not out.resolve().is_relative_to(BASE) or not out.is_dir():raise ValueError('Unowned output path')
    lock=json.loads((ROOT/'extensions/rl-lqr/runtime-lock.json').read_text())
    for name,version in lock['versions'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('Runtime mismatch: '+name)
    for name,value in lock['files'].items():
        if hashlib.sha256((ROOT/lock['overlay']/name).read_bytes()).hexdigest()!=value:raise ValueError('Runtime overlay changed')
    if op=='engineering':
        roster=[EXT/'tests/test_reference.py',EXT/'tests/test_learner.py']
        subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
            '--basetemp='+str(out/'pytest'),'--junitxml='+str(out/'tests.xml'),*map(str,roster)],check=True,timeout=550)
        suites=list(ET.parse(out/'tests.xml').getroot().iter('testsuite'))
        if not suites or any(int(s.get('skipped',0)) for s in suites):raise ValueError('Tests skipped')
        from hponas_rl_lqr10.reference import oracle_report
        result=dict(passed=True,tests=sum(int(s.get('tests',0)) for s in suites),oracle=oracle_report())
        (out/'engineering-result.json').write_text(json.dumps(result,indent=2)+'\n')
    else:
        from hponas_rl_lqr10.operations import study,audit,master_audit
        {'study':study,'audit':audit,'master-audit':master_audit}[op](out)

if __name__=='__main__':main()
