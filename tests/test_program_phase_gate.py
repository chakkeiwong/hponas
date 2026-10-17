"""Adversarial scope-binding checks; no scientific campaign is executed."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import program_state as p


class PhaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = {'status': 'DRAFT', 'entries': {
            'V01': {'claim': 'finite conformance'}, 'V16': {'claim': 'audit'},
            'V12': {'claim': 'later warm starts'}}}
        self.write('validation/evidence.py', 'TIER0 = ("V01",)\n')
        self.write('validation/protocols.json', self.registry)
        self.write('pyproject.toml', '[project]\nname="fixture"\n')
        self.write('requirements.txt', '')
        bindings, entries = [], {}
        for vid in ('V01', 'V16'):
            name = f'validation/protocols/{vid.lower()}_protocol.md'
            self.write(name, 'exact original rules')
            bindings.append({'id': vid, 'identity': 'aligned', 'protocol_path': name})
            entries[vid] = {'registry_entry_sha256': p.canonical_digest(self.registry['entries'][vid]),
                            'protocol_path': name, 'protocol_sha256': p.sha256(self.root / name)}
        self.binding = {'kind': 'phase_protocol_binding_v1', 'phase': 'tier0',
                        'source_digest': p.source_digest(self.root),
                        'register_sha256': p.sha256(self.root / 'validation/protocols.json'),
                        'entries': entries}
        self.data = {'evidence': [], 'protocol_phase_bindings': {'tier0': 'E-PHASE'},
                     'protocol_bindings': bindings, 'tier0_campaigns': ['V01'], 'audit_gate': 'V16',
                     'work_items': [
                         {'id': 'W', 'phase': 'tier0', 'state': 'complete', 'dependencies': [], 'decision_dependencies': []},
                         {'id': 'REL-01', 'phase': 'tier0', 'state': 'blocked', 'dependencies': ['W'], 'decision_dependencies': []}],
                     'decisions': [{'id': d, 'status': 'accepted'} for d in ('D-PROTOCOL', 'D-TIERS')],
                     'requirements': []}
        self.bind()

    def write(self, name, value):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value if isinstance(value, str) else json.dumps(value))

    def bind(self):
        self.write('evidence/phase.json', self.binding)
        self.data['evidence'] = [{'id': 'E-PHASE', 'kind': 'phase_protocol_binding',
            'path': 'evidence/phase.json', 'sha256': p.sha256(self.root / 'evidence/phase.json')}]

    def blockers(self):
        return p.tier0_protocol_scope_blockers(self.root, self.data, self.registry)

    def test_exact_active_phase_can_coexist_with_later_drafts(self):
        self.assertEqual(self.blockers(), [])
        self.assertEqual(self.registry['status'], 'DRAFT')

    def test_wrong_or_missing_bindings_fail_closed(self):
        original = copy.deepcopy(self.binding)
        for fault in ['missing-audit', 'extra-entry', 'wrong-phase', 'wrong-source', 'wrong-register', 'wrong-rule']:
            with self.subTest(fault=fault):
                self.binding = copy.deepcopy(original)
                if fault == 'missing-audit': del self.binding['entries']['V16']
                if fault == 'extra-entry': self.binding['entries']['V12'] = {}
                if fault == 'wrong-phase': self.binding['phase'] = 'tier1'
                if fault == 'wrong-source': self.binding['source_digest'] = '0' * 64
                if fault == 'wrong-register': self.binding['register_sha256'] = '0' * 64
                if fault == 'wrong-rule': self.binding['entries']['V01']['protocol_sha256'] = '0' * 64
                self.bind()
                self.assertTrue(self.blockers())

    def test_unbound_changed_and_escaped_evidence_is_refused(self):
        original = copy.deepcopy(self.data)
        for fault in ['missing', 'wrong-kind', 'changed', 'escaped']:
            with self.subTest(fault=fault):
                self.data = copy.deepcopy(original)
                if fault == 'missing': self.data['protocol_phase_bindings'].clear()
                if fault == 'wrong-kind': self.data['evidence'][0]['kind'] = 'human-approval'
                if fault == 'changed': self.data['evidence'][0]['sha256'] = '0' * 64
                if fault == 'escaped': self.data['evidence'][0]['path'] = '../unbound.json'
                self.assertTrue(self.blockers())

    def test_protocol_and_source_drift_are_refused(self):
        self.write('validation/protocols/v01_protocol.md', 'changed criterion')
        self.assertTrue(self.blockers())

    def test_malformed_binding_objects_are_refused(self):
        self.binding = []
        self.bind()
        self.assertTrue(self.blockers())
        self.data['protocol_phase_bindings'] = None
        self.assertTrue(self.blockers())

    def test_unresolved_identity_is_not_cured_by_a_scope_binding(self):
        self.data['protocol_bindings'][0]['identity'] = 'unresolved'
        self.assertTrue(self.blockers())

    def test_existing_complete_global_freeze_still_uses_existing_path(self):
        self.registry['status'] = 'FROZEN'
        self.data.pop('protocol_phase_bindings')
        self.assertEqual(self.blockers(), [])

    def test_scope_binding_cannot_bypass_other_release_guards(self):
        original = copy.deepcopy(self.data)
        for fault in ['unfinished-work', 'open-decision', 'unresolved-requirement', 'stale-result', 'failing-result', 'missing-audit']:
            with self.subTest(fault=fault):
                self.data = copy.deepcopy(original)
                campaign = {'id': 'V01', 'fresh': True, 'verdict': 'PASS', 'audit_passed': True}
                if fault == 'unfinished-work': self.data['work_items'][0]['state'] = 'blocked'
                if fault == 'open-decision': self.data['decisions'][0]['status'] = 'open'
                if fault == 'unresolved-requirement':
                    self.data['requirements'] = [{'id': 'R', 'title': 'remaining contract', 'disposition': 'unresolved', 'work_items': ['W']}]
                if fault == 'stale-result': campaign['fresh'] = False
                if fault == 'failing-result': campaign['verdict'] = 'INCONCLUSIVE'
                if fault == 'missing-audit': campaign['audit_passed'] = False
                view = {'program': self.data, 'campaigns': [campaign]}
                with patch.object(p, 'check', return_value=([], view)):
                    self.assertTrue(p.tier0_release_blockers(self.root))


if __name__ == '__main__':
    unittest.main()
