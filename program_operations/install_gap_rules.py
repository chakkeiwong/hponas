#!/usr/bin/python3 -I
"""Install one additive pinned rule file; never edit default/global rules."""
import importlib.util
import json
import hashlib
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import uuid4
BASE=Path('/home/ubuntu/workspace/hponas/program_operations')
PINS={'hponas-gap-closure.rules': 'b03cf0ed46f33deb8f04a0e594a0ba18776337ac28e3f5f8fa49a48ebdade01c', 'gap_ops.py': '67b3df16cd500f98757251e0cea05cab7bb745a1ef9bf9e205672ad9c6193d78', 'gap_audit.py': '4e5ddc6ce2c4a990b4ef21b04cb8f54574b37e91a6bace5a73f2ef87c6766f86', 'check_gap_rules.py': '04f780da9d200b998d4ec370de23bf6426e9bd910e6c40f6016cefe780b6829e', 'test_gap_operations.py': 'a7e58e635b19a3c1f26fc18cf43473e13ea239d2caebe066b6c02bcbb0eb4757', 'hponas_ops.py': 'a9d32d1992e8de049680bdd00d738205e240fb20f3f79d45037d86d33effe940', 'check_approval_rules.py': '86ce9e3e19d9392a6cfa0cfcabe710712ed435e32a901284b761b1f3c3811322', 'install_approval_rules.py': 'f3a16f9b02c982ec90bc76ab2030882f8d842f3bf42dcecc94bf8925d25831fb'}
DESTINATION=Path('/home/ubuntu/.codex/rules/hponas-gap-closure.rules')

def module(name):
    spec=importlib.util.spec_from_file_location(name,BASE/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def main():
    if len(sys.argv)!=1:return 2
    for name,expected in PINS.items():
        path=BASE/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Unreviewed install input: '+name)
    checked=module('check_gap_rules').check()
    payload=(BASE/'hponas-gap-closure.rules').read_bytes()
    if hashlib.sha256(payload).hexdigest()!=PINS['hponas-gap-closure.rules']:
        raise ValueError('Candidate changed after matcher review')
    status=module('install_approval_rules').write_pinned(payload,DESTINATION)
    output=BASE.parent/'docs/program/operations-runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-gap-rules-install-'+uuid4().hex[:8]+'.json')
    result={'status':status,'destination':str(DESTINATION),'sha256':PINS['hponas-gap-closure.rules'],'pins':PINS,'validated_cases':len(checked['cases']),'default_rules_modified':False,'host_live_reload_verified':False}
    with output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({**result,'receipt':str(output.relative_to(BASE.parent))},indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
