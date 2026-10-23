#!/usr/bin/python3 -I
"""Independent admission and false-completion counterexamples for GAP-01."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

BASE=Path('/home/ubuntu/workspace/hponas/program_operations')
def module(name):
    spec=importlib.util.spec_from_file_location(name,BASE/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
gap=module('gap_ops');audit=module('gap_audit')


class Boundaries(unittest.TestCase):
    def test_rejects_args_without_execution(self):
        for args in ([],['test-mo','extra'],['run-campaign'],['execute-python','/tmp/a.py'],['test-mo; git push']):
            result=subprocess.run(['/usr/bin/python3','-I',str(BASE/'gap_ops.py'),*args],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,2)

    def test_all_rosters_are_fixed_and_exist(self):
        for op in gap.OPERATIONS:
            for command in gap.commands(op):
                self.assertNotIn('bash',command)
                self.assertTrue(Path(command[0]).is_absolute())
        for paths in gap.TESTS.values():
            for path in paths:self.assertTrue((BASE.parent/path).is_file(),path)

    def test_original_inventory_cannot_be_deleted_or_self_certified(self):
        original=json.loads((BASE.parent/'docs/program/gap_closure.json').read_text())
        program=json.loads((BASE.parent/'docs/program/program.json').read_text())
        audit.validate(original,program)
        for kind in ('omit','duplicate','owner','source','exclude','final','unbound'):
            data=copy.deepcopy(original);p=copy.deepcopy(program)
            if kind=='omit':data['clauses'].pop()
            if kind=='duplicate':data['clauses'].append(data['clauses'][0])
            if kind=='owner':data['clauses'][0]['owner']='missing'
            if kind=='source':data['clauses'][0]['original_source']='absent'
            if kind=='exclude':data['clauses'][0]['scope']='waived'
            if kind=='final':data['final_stage']='GAP-01/INTEGRATION-REVIEW'
            if kind=='unbound':data['clauses'][0]['evidence']=[{'path':'AGENTS.md','sha256':'0'*64}]
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError,OSError)):
                audit.validate(data,p)
        with self.assertRaises(ValueError):audit.validate(original,program,final=True)


if __name__=='__main__':unittest.main()
