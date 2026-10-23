#!/usr/bin/python3 -I
"""Permission-boundary, timeout and overwrite-refusal checks; no campaigns."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import json
import hashlib
from copy import deepcopy

BASE = Path('/home/ubuntu/workspace/hponas/program_operations')


def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


ops = module('hponas_ops')
installer = module('install_approval_rules')
services = module('local_services')
run_status = module('run_status')
collection = module('check_collection')
trace_spec = importlib.util.spec_from_file_location('product_trace',BASE.parent/'tools/product_trace.py')
trace = importlib.util.module_from_spec(trace_spec)
trace_spec.loader.exec_module(trace)


class OperationBoundary(unittest.TestCase):
    def test_collection_check_rejects_eager_objects_and_accepts_deferred_factories(self):
        eager = [
            "from hponas import Knob\nvalue = Knob('x', 'ordinal', (0, 1))",
            "from hponas import Knob as K\nfactory = K\nvalue = factory('x', 'ordinal', (0, 1))",
            "import hponas.space\nvalue = hponas.space.Knob('x', 'ordinal', (0, 1))",
            "from hponas import Knob\ndef test_case(value=Knob('x', 'ordinal', (0, 1))): pass",
            "from hponas import Knob\nfactory = lambda value=Knob('x', 'ordinal', (0, 1)): value",
            "from hponas import Knob\nclass Cases:\n value = Knob('x', 'ordinal', (0, 1))",
            "def fixture(): return object()\nvalue = fixture()",
            "class Error(Exception):\n def __init__(self): arbitrary()\nvalue = Error()",
            "from hponas import Knob\n@pytest.mark.parametrize('x', [Knob('x', 'ordinal', (0, 1))])\ndef test_case(x): pass",
        ]
        for source in eager:
            with self.subTest(source=source):
                self.assertTrue(any(not row['allowed'] for row in collection.collection_calls(source)))
        deferred = [
            "from hponas import Knob\nfactory = lambda: Knob('x', 'ordinal', (0, 1))",
            "from hponas import Knob\ndef test_case():\n value = Knob('x', 'ordinal', (0, 1))",
            "class Error(Exception): pass\nclass Deadline(Error): pass\nvalue = Deadline('test')",
            "from hypothesis import strategies as st\n@st.composite\ndef spaces(draw): return object()\n@given(spaces())\ndef test_case(space): pass",
        ]
        for source in deferred:
            with self.subTest(source=source):
                self.assertFalse(any(not row['allowed'] for row in collection.collection_calls(source)))

    def test_liveness_requires_fresh_heartbeat_boot_namespace_and_process_identity(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        host = dict(boot_id='current-boot', pid_namespace='pid:[17]')
        start = dict(**host,process=dict(pid=42,start_ticks=123))
        health = dict(utc=now.isoformat(),reason=None)
        live = lambda pid:dict(pid=pid,start_ticks=123,state='S')
        def observe(s=start,h=health,t=None,p=live):
            return run_status.classify(s,h,t,now=now,current_host=host,process=p)
        self.assertTrue(observe()['running'])
        for status,kwargs in (
            ('interrupted_by_reboot',dict(s=dict(start,boot_id='old-boot'))),
            ('process_namespace_not_visible',dict(s=dict(start,pid_namespace='pid:[9]'))),
            ('legacy_identity_unverified',dict(s={'process':start['process']})),
            ('heartbeat_stale_or_clock_changed',dict(h={'utc':(now-timedelta(seconds=91)).isoformat()})),
            ('heartbeat_stale_or_clock_changed',dict(h={'utc':(now+timedelta(seconds=6)).isoformat()})),
            ('supervisor_not_live',dict(p=lambda pid:None)),
            ('supervisor_not_live',dict(p=lambda pid:dict(pid=pid,start_ticks=124,state='S'))),
            ('supervisor_not_live',dict(p=lambda pid:dict(pid=pid,start_ticks=123,state='Z'))),
            ('heartbeat_missing',dict(h=None)),
            ('guard_intervention',dict(h=dict(health,reason='low_disk'))),
            ('terminal_failure_recorded',dict(t=dict(status='REPAIR_REQUIRED'))),
            ('terminal_completion_recorded',dict(t=dict(status='COMPLETE'))),
        ):
            with self.subTest(status=status):
                result=observe(**kwargs)
                self.assertEqual(result['status'],status)
                self.assertFalse(result['running'])
                self.assertFalse(result['scientific_acceptance'])
        self.assertTrue(observe(t=dict(status='pending',passed=False))['running'])

    def test_last_heartbeat_read_is_bounded_and_refuses_partial_writes(self):
        with tempfile.TemporaryDirectory(dir=BASE) as tmp:
            path=Path(tmp)/'health.jsonl'
            path.write_text('x'*100000+'\n'+json.dumps({'utc':'last'})+'\n')
            self.assertEqual(run_status.last_health(path),{'utc':'last'})
            path.write_text('{"utc":')
            with self.assertRaises(ValueError):run_status.last_health(path)

    def test_cli_rejects_unapproved_arguments_before_execution(self):
        cases = [[], ['unknown'], ['checks', 'extra.py'], ['status', ';', 'git', 'push'],
                 ['execute-python', '/tmp/payload.py'], ['checks; touch /tmp/payload']]
        for args in cases:
            with self.subTest(args=args):
                result = subprocess.run(['/usr/bin/python3', '-I', str(BASE / 'hponas_ops.py'), *args],
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2)
        for script in ('install_approval_rules.py', 'check_approval_rules.py'):
            result = subprocess.run(['/usr/bin/python3', '-I', str(BASE / script), '/tmp/override'],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)

    def test_installer_does_not_overwrite_other_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'candidate.rules'
            self.assertEqual(installer.write_pinned(b'reviewed', target), 'installed')
            self.assertEqual(installer.write_pinned(b'reviewed', target), 'already_installed')
            with self.assertRaises(ValueError):
                installer.write_pinned(b'different', target)
            self.assertEqual(target.read_bytes(), b'reviewed')
            link = Path(tmp) / 'symlink.rules'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                installer.write_pinned(b'reviewed', link)
            self.assertEqual(target.read_bytes(), b'reviewed')

    def test_timeout_terminates_owned_process_and_retains_failure(self):
        with tempfile.TemporaryDirectory(dir=BASE) as tmp:
            log = Path(tmp) / 'timeout.log'
            row = ops.run_child(['/usr/bin/python3', '-I', '-c', 'import time; time.sleep(10)'],
                                log, ops.environment(), timeout=0.1)
            self.assertTrue(row['timed_out'])
            self.assertNotEqual(row['returncode'], 0)
            self.assertLess(row['elapsed_seconds'], 8)

    def test_scientific_test_rosters_exist_and_no_shell_forwarding(self):
        for operation in ops.TESTS:
            for path in ops.TESTS[operation]:
                self.assertTrue((ops.ROOT / path).is_file(), path)
            expected = {
                'test-search': [
                    ['/usr/bin/python3','-I',str(BASE/'check_collection.py')],
                    ['/usr/bin/python3','-I',str(BASE/'check_proof_context.py')],
                ],
                'test-study': [
                    [ops.PYTHON,str(BASE/'local_services.py'),'ray'],
                    [ops.PYTHON,str(BASE/'local_services.py'),'ray-repeated'],
                ],
                'test-store': [[ops.PYTHON,str(BASE/'local_services.py'),'postgres']],
            }.get(operation, [])
            actual = [command for command in ops.commands(operation) if command[1:3] != ['-m', 'pytest']]
            self.assertEqual(actual, expected)
            pytest_commands = [command for command in ops.commands(operation) if command[1:3] == ['-m', 'pytest']]
            self.assertEqual(tuple(path for command in pytest_commands for path in command[6:]), ops.TESTS[operation])
            self.assertEqual(len(pytest_commands), 3 if operation == 'test-search' else 1)
        self.assertNotIn('run-campaign', ops.OPERATIONS)

    def test_live_modes_reject_arbitrary_commands_and_skipped_evidence(self):
        for args in ([],['unknown'],['ray','extra'],['postgres','--dsn=external']):
            with self.assertRaises(ValueError):
                services.mode_from_args(args)
        self.assertEqual(set(services.ROSTERS), {'postgres','ray','ray-repeated'})
        ray_cases = services.ROSTERS['ray'] + services.ROSTERS['ray-repeated']
        self.assertEqual(ray_cases, (
            'tests/integration/test_ray_streaming.py',
            'tests/integration/test_declared_ray.py::test_live_declared_ray_metered_artifact_roles_and_resume',
            'tests/integration/test_declared_ray.py::test_live_ray_repeated_barriers_preserve_vector_and_scalar_roles',
        ))
        with tempfile.TemporaryDirectory(dir=BASE) as tmp:
            path = Path(tmp)/'tests.xml'
            path.write_text('<testsuites><testsuite><testcase/><testcase><skipped/></testcase></testsuite></testsuites>')
            self.assertEqual(services.test_counts(path),dict(tests=2,skipped=1,failure=0,error=0))

    def test_semantic_trace_refuses_omissions_drift_and_false_completion(self):
        with tempfile.TemporaryDirectory(dir=BASE) as tmp:
            root = Path(tmp)
            def save(name,value):
                path = root/name
                path.write_text(json.dumps(value))
                return dict(path=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            basis = save('basis.json',{'finite':'evidence'})
            source = {
                'interface_clauses':[{'id':'C01'}],
                'legacy_product_rows':[{'legacy_row':1}],
                'build_v3_components':[{'original_tier':'Tier 0','component':'Study'}],
                'recovery_approval_items':[{'requirement':{'id':'APP-01'}}],
                'deferred_dispositions':[{'requirement':'REQ-01'}],
            }
            inventory = save('inventory.json',source)
            groups = {key:[dict(source_key=trace.row_key(key,rows[0]),status='development_verified',
                behavior='Known arithmetic aggregation',scope='finite local',owners=['PRD-01'],
                qualification_owner='PRD-01/INTEGRATED-PRODUCT-REVIEW',evidence_refs=['basis'],
                code_paths=['basis.json'],test_paths=['basis.json'],resource_anchor='basis.json')]
                for key,rows in source.items()}
            report = dict(kind='semantic_product_trace_v1',original_inventory=inventory,groups=groups)
            program = dict(work_items=[dict(id='PRD-01',state='in_progress')],
                continuation={'steps':[dict(id='PRD-01/INTEGRATED-PRODUCT-REVIEW')]},
                evidence=[dict(id='basis',**basis)],semantic_product_trace='trace')
            def check(value, state=None):
                candidate = deepcopy(program if state is None else state)
                candidate['evidence'].append(dict(id='trace',**save('trace.json',value)))
                return trace.validate_trace(root,candidate)
            check(report)
            for kind in ('omit','duplicate','owner','evidence','stage','code','scope','open'):
                changed=deepcopy(report)
                row=changed['groups']['interface_clauses'][0]
                state=deepcopy(program)
                if kind=='omit': changed['groups']['interface_clauses'].clear()
                if kind=='duplicate': changed['groups']['interface_clauses'].append(deepcopy(row))
                if kind=='owner': row['owners']=['missing']
                if kind=='evidence': row['evidence_refs']=['missing']
                if kind=='stage': row['qualification_owner']='missing'
                if kind=='code': row['code_paths']=[]
                if kind=='scope': row['scope']=''
                if kind=='open':
                    row['status']='open';state['work_items'][0]['state']='complete'
                with self.subTest(kind=kind),self.assertRaises(ValueError): check(changed,state)
            (root/'basis.json').write_text('changed')
            with self.assertRaisesRegex(ValueError,'bytes differ'): check(report)
            state=deepcopy(program);state.pop('semantic_product_trace');state['work_items'][0]['state']='complete'
            with self.assertRaisesRegex(ValueError,'requires semantic'):trace.validate_trace(root,state)
            state['work_items']=[]
            trace.validate_trace(root,state)  # A historical pre-product register remains readable.


if __name__ == '__main__':
    unittest.main(argv=['test_operations'], verbosity=2)
