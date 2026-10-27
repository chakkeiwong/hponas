"""Run the fixed installed roster in a fresh outside-checkout directory."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-delivery-03'

def run(out):
    completed=json.loads((BASE/'delivery-completion.json').read_text())
    result=json.loads((ROOT/completed['directory']/'result.json').read_text())
    py=ROOT/result['python']
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    with tempfile.TemporaryDirectory(prefix='hponas-sci03-roster-',dir='/tmp') as d:
        cp=subprocess.run([str(py),'-I',str(ROOT/'hpo-survey/repairs/sci03/installed_roster.py'),str(out)],cwd=d,env=env,timeout=570)
        if cp.returncode:raise RuntimeError('Installed roster failed')
    if not json.loads((out/'result.json').read_text())['mechanics_passed']:raise AssertionError('Missing complete roster')

if __name__=='__main__':run(Path(sys.argv[1]))
