#!/usr/bin/python3 -I
"""Fixed zero-training publication for completed RL-LQR-05 evidence."""
from pathlib import Path
import hashlib
import json
import os
import runpy
import sys

ROOT=Path('/home/ubuntu/workspace/hponas')
if len(sys.argv)!=1:raise ValueError('No additional arguments accepted')
program=json.loads((ROOT/'docs/program/program.json').read_text())
step=next(s for s in program['continuation']['steps'] if s['id']=='RL-LQR-05/STUDY')
if step['state']!='complete':raise ValueError('Study must finish before documentation')
manifest_path=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-05/documentation-manifest.json'
manifest=json.loads(manifest_path.read_text())
for b in manifest['inputs']:
    if hashlib.sha256((ROOT/b['path']).read_bytes()).hexdigest()!=b['sha256']:raise ValueError('Documentation source differs')
runpy.run_path(str(ROOT/'extensions/rl-lqr-multi/report.py'),run_name='__main__')
