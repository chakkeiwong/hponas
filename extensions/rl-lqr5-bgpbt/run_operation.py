"""Fixed stage entry points; all resources and source identities owned by runner."""
from pathlib import Path
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
EXT=ROOT/'extensions/rl-lqr5-bgpbt'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-03'


def engineering(out,repair=False):
    roster=[EXT/'tests'/n for n in ('test_adapter.py','test_explorer.py','test_tasks.py','test_study.py')]
    if repair: roster.append(EXT/'tests/test_repair.py')
    subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        '--basetemp='+str(out/'pytest'),'--junitxml='+str(out/'tests.xml'),
        *map(str,roster)],check=True,timeout=550)
    suites=list(ET.parse(out/'tests.xml').getroot().iter('testsuite'))
    if not suites or any(int(s.get('skipped',0)) for s in suites): raise ValueError('Skipped tests')
    result={'passed':True,'tests':sum(int(s.get('tests',0)) for s in suites),
            'scope':'SAC state/search/distillation/recovery and actual CPU concurrency'}
    (out/'engineering-result.json').write_text(json.dumps(result,indent=2)+'\n')


def main():
    op,out=sys.argv[1],Path(sys.argv[2])
    if not out.resolve().is_relative_to(BASE) or not out.is_dir(): raise ValueError('Output escapes owned evidence')
    # Same pinned dependency overlay as RL-LQR-01/02.
    import importlib.metadata,hashlib
    lock=json.loads((ROOT/'extensions/rl-lqr/runtime-lock.json').read_text())
    for name,version in lock['versions'].items():
        if importlib.metadata.version(name)!=version: raise ValueError('Runtime version differs: '+name)
    for name,value in lock['files'].items():
        if hashlib.sha256((ROOT/lock['overlay']/name).read_bytes()).hexdigest()!=value:
            raise ValueError('Runtime overlay differs: '+name)
    if op=='device-repair':
        roster=[EXT/'tests/test_adapter.py',EXT/'tests/test_local_learner.py']
        subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
            '--basetemp='+str(out/'pytest'),'--junitxml='+str(out/'tests.xml'),
            *map(str,roster)],check=True,timeout=240)
        suites=list(ET.parse(out/'tests.xml').getroot().iter('testsuite'))
        if sum(int(s.get('tests',0)) for s in suites)!=8 or any(int(s.get('skipped',0)) for s in suites):
            raise ValueError('Device repair roster incomplete')
        (out/'device-repair-result.json').write_text(json.dumps({'passed':True,'tests':8})+'\n')
    elif op in ('engineering','repair-engineering'): engineering(out,op=='repair-engineering')
    else:
        from hponas_rl_bgpbt.operations import OPERATIONS
        OPERATIONS[op](out)


if __name__=='__main__': main()
