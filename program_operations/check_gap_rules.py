#!/usr/bin/python3 -I
"""Review exact GAP command rules with the installed rule matcher."""
import importlib.util
import json
from pathlib import Path
import sys

BASE=Path('/home/ubuntu/workspace/hponas/program_operations')
def module(name):
    spec=importlib.util.spec_from_file_location(name,BASE/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
gap=module('gap_ops')
matcher=module('check_approval_rules')
CANDIDATE=BASE/'hponas-gap-closure.rules'
DESTINATION=Path('/home/ubuntu/.codex/rules/hponas-gap-closure.rules')


def cases():
    runner=str(BASE/'gap_ops.py');installer=str(BASE/'install_gap_rules.py')
    rows=[]
    for argv in [[runner,op] for op in gap.OPERATIONS]+[[installer]]:
        rows.append((argv,True))
        for flag in ('-c','-lc'): rows.append((['/bin/bash',flag,' '.join(argv)],True))
    for argv in ([runner], [runner,'run-campaign'], [runner,'execute-python','/tmp/a.py'],
                 ['/usr/bin/python3',runner,'test-mo'],['git','push'],
                 ['/bin/bash','-c',runner+' test-mo; git push'],
                 ['/bin/bash','-lc','env EXTRA=1 '+runner+' test-mo'],
                 ['/usr/bin/env','EXTRA=1',runner,'test-mo'],['python','-c','print(1)']):
        rows.append((argv,False))
    return rows


def check():
    matcher.cases=cases
    return matcher.check(CANDIDATE)


def main():
    if len(sys.argv)!=1:return 2
    result=check()
    result['installed_bytes_match']=DESTINATION.is_file() and DESTINATION.read_bytes()==CANDIDATE.read_bytes()
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
