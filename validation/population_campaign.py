"""Frozen, once-only V08 generation and bounded raw-evidence reconstruction."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import time

from validation.evidence import ROOT, digest, source_digest
from validation.population_contract import CLAIM, contract
from validation.population_producers import execute_slot
from validation.population_reference import verify_slot
from validation.stylized_campaign import bounded_seconds
from validation.tier1_campaign import require_runtime, first_difference


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def binding(path):
    return {'path': str(Path(path).resolve()), 'sha256': digest(path)}


def read_binding(item, directory):
    path = Path(item['path']).resolve()
    if not path.is_relative_to(Path(directory).resolve()) or digest(path) != item['sha256']:
        raise ValueError('Changed or external population artifact')
    return json.loads(path.read_text())


def allocation():
    return {'generation': 1, 'reconstructions': 3, 'processes': 2,
            'wall_seconds_per_process': 300, 'maximum_phase_seconds': 600,
            'cpu_affinity_count': 1, 'numerical_threads': 1, 'gpu': False,
            'maximum_gradient_update_attempts_including_replays': 128}


def require_phase():
    from tools.program_state import canonical_digest
    program = json.loads((ROOT/'docs/program/program.json').read_text())
    decisions = {d['id']: d['status'] for d in program['decisions']}
    stages = {s['id']: s['state'] for s in program['continuation']['steps']}
    if decisions.get('D-PROTOCOL-T2') != 'accepted' or stages.get('T2-POP/PROTOCOL-FREEZE') != 'complete':
        raise ValueError('Population phase is not frozen')
    ident = program['protocol_phase_bindings'].get('tier2')
    rows = [e for e in program['evidence'] if e['id'] == ident]
    if len(rows) != 1:
        raise ValueError('Population phase binding is missing')
    path = ROOT/rows[0]['path']
    if digest(path) != rows[0]['sha256']:
        raise ValueError('Population phase binding changed')
    phase = json.loads(path.read_text())
    registry = json.loads((ROOT/'validation/protocols.json').read_text())
    if (phase.get('kind') != 'population_finite_phase_v1' or phase.get('source_digest') != source_digest()
            or phase.get('registry_sha256') != digest(ROOT/'validation/protocols.json')
            or phase.get('registry_entry_sha256') != canonical_digest(registry['entries']['V08'])
            or phase.get('protocol_sha256') != digest(ROOT/'validation/protocols/v08_protocol.md')
            or phase.get('contract') != contract() or phase.get('runtime') != require_runtime()
            or phase.get('allocation') != allocation()
            or phase.get('resource_authorization') != 'standing_user_bounded_local_known_answer_execution'):
        raise ValueError('Population source/runtime/protocol/allocation differs')
    if registry['entries']['V08'].get('contract') != contract():
        raise ValueError('Population registry contract differs')
    name = phase.get('run_name')
    if not isinstance(name, str) or not name or Path(name).name != name or name in {'.', '..'}:
        raise ValueError('Unsafe population run allocation')
    return {**binding(path), 'run_path': str((ROOT/'validation/artifacts/V08'/name).resolve())}


def require_run(directory):
    phase = require_phase()
    if str(Path(directory).resolve()) != phase['run_path']:
        raise ValueError('Population run differs from once-only allocation')
    return phase


def campaign(directory):
    directory = Path(directory).resolve()
    phase = require_run(directory)
    spec = contract()
    freeze = {'contract': spec, 'source_digest': source_digest(), 'runtime': require_runtime(),
              'protocol_sha256': digest(ROOT/'validation/protocols/v08_protocol.md'),
              'registry_sha256': digest(ROOT/'validation/protocols.json'),
              'run_dir': str(directory), 'phase': phase}
    write_new(directory/'population-freeze.json', freeze)
    write_new(directory/'generation-start.json', {'created_utc': datetime.now(timezone.utc).isoformat(),
                                                 'freeze': binding(directory/'population-freeze.json')})
    started = time.monotonic()
    records, exhausted = [], False
    with (directory/'slot-journal.jsonl').open('x') as journal:
        def event(value):
            journal.write(json.dumps(value, allow_nan=False)+'\n')
            journal.flush(); os.fsync(journal.fileno())
        with bounded_seconds(spec['wall_seconds_per_process']):
            for index, slot in enumerate(spec['slots']):
                item = {'slot': slot, 'status': 'incomplete', 'raw': None, 'error': None}
                event({'action': 'start', 'index': index, 'slot': slot})
                if exhausted:
                    item['error'] = 'prior_deadline_exhausted'
                else:
                    try:
                        raw = execute_slot(slot, directory/f'slot-{index:03d}')
                        path = directory/f'raw-{index:03d}.json'
                        write_new(path, raw)
                        item.update(status='complete', raw=binding(path))
                    except Exception as exc:
                        item['error'] = f'{type(exc).__name__}: {exc}'
                        exhausted = isinstance(exc, TimeoutError)
                records.append(item)
                path = directory/f'slot-receipt-{index:03d}.json'
                write_new(path, item)
                event({'action': 'end', 'index': index, 'receipt': binding(path)})
    write_new(directory/'slots.json', records)
    return {'schema_version': 1, 'validation_id': 'V08', 'claim': CLAIM, 'run_dir': str(directory),
            'freeze': binding(directory/'population-freeze.json'), 'slots': binding(directory/'slots.json'),
            'journal': binding(directory/'slot-journal.jsonl'), 'generation_seconds': time.monotonic()-started}


def consume_reconstruction(directory):
    """Exclusive durable start consumes a slot even if the process then crashes."""
    for index in range(1, contract()['maximum_reconstructions']+1):
        path = directory/f'reconstruction-{index:02d}-start.json'
        try:
            write_new(path, {'index': index, 'created_utc': datetime.now(timezone.utc).isoformat(),
                             'source_digest': source_digest(), 'runtime': require_runtime()})
            return index
        except FileExistsError:
            continue
    raise ValueError('Population reconstruction allocation exhausted')


def verify_artifacts(raw, directory):
    if 'files' not in raw:
        return
    names = {str(path.relative_to(directory)) for path in directory.rglob('*.json')}
    if names != set(raw['files']):
        raise ValueError('Population checkpoint inventory differs')
    for name, expected in raw['files'].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory.resolve()) or json.loads(path.read_text()) != expected:
            raise ValueError('Population checkpoint differs from retained raw evidence')


def _reconstruct(result, directory):
    freeze = read_binding(result['freeze'], directory)
    spec = contract()
    if (freeze['contract'] != spec or freeze['source_digest'] != source_digest()
            or freeze['runtime'] != require_runtime() or freeze['run_dir'] != str(directory)
            or freeze['phase'] != require_phase()
            or freeze['registry_sha256'] != digest(ROOT/'validation/protocols.json')
            or freeze['protocol_sha256'] != digest(ROOT/'validation/protocols/v08_protocol.md')):
        raise ValueError('Population freeze/source/runtime differs')
    records = read_binding(result['slots'], directory)
    if [row['slot'] for row in records] != spec['slots']:
        raise ValueError('Population ordered complete roster differs')
    journal_path = Path(result['journal']['path']).resolve()
    if not journal_path.is_relative_to(directory) or digest(journal_path) != result['journal']['sha256']:
        raise ValueError('Population slot journal differs')
    journal = [json.loads(line) for line in journal_path.read_text().splitlines()]
    if len(journal) != 2*len(records):
        raise ValueError('Population incremental event coverage differs')
    seconds = result['generation_seconds']
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Invalid measured generation duration')
    incomplete = seconds > spec['wall_seconds_per_process']
    reports = []
    for index, (slot, record) in enumerate(zip(spec['slots'], records)):
        if journal[2*index] != {'action': 'start', 'index': index, 'slot': slot}:
            raise ValueError('Population slot start differs')
        end = journal[2*index+1]
        if end['action'] != 'end' or end['index'] != index or read_binding(end['receipt'], directory) != record:
            raise ValueError('Population slot end differs')
        if record['status'] != 'complete':
            incomplete = True
            continue
        if record['error'] is not None:
            raise ValueError('Completed population slot has an error')
        raw = read_binding(record['raw'], directory)
        verify_artifacts(raw, directory/f'slot-{index:03d}')
        report = verify_slot(slot, raw)
        with tempfile.TemporaryDirectory(prefix='population-identity-') as temporary:
            replay = execute_slot(slot, Path(temporary)/'slot')
        difference = first_difference(replay, raw)
        if difference:
            raise ValueError('Production method/seed/recovery identity differs at '+difference)
        reports.append({'slot': slot['id'], **report})
    if not incomplete:
        if sum(r['updates_lower'] for r in reports) != 31 or sum(r['updates_upper'] for r in reports) != 32:
            raise ValueError('Full population physical work allocation differs')
    return {'verdict': 'INCONCLUSIVE' if incomplete else 'PASS', 'reports': reports,
            'scope': 'exposed_finite_local_conformance_only', 'default_activation': False,
            'integrated_release_accepted': False, 'method_identity_verified': not incomplete}


def reconstruct(result):
    if (result.get('schema_version') != 1 or result.get('claim') != CLAIM
            or result.get('validation_id') != 'V08'):
        raise ValueError('Unknown population result schema')
    directory = Path(result['run_dir']).resolve()
    require_run(directory)
    index = consume_reconstruction(directory)
    try:
        with bounded_seconds(contract()['wall_seconds_per_process']):
            report = _reconstruct(result, directory)
    except TimeoutError as exc:
        report = {'verdict': 'INCONCLUSIVE', 'reason': str(exc), 'method_identity_verified': False}
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        report = {'verdict': 'FAIL', 'reason': f'{type(exc).__name__}: {exc}', 'method_identity_verified': False}
    write_new(directory/f'reconstruction-{index:02d}-result.json', report)
    return report


def recompute_result(result):
    return reconstruct(result)['verdict']
