"""Once-only finite V12 campaign, frozen before training and raw reconstruction."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

from validation.evidence import ROOT, digest, source_digest
from validation.population_campaign import write_new, binding, read_binding
from validation.stylized_campaign import bounded_seconds
from validation.tier1_campaign import require_runtime
from validation.warm_finite_contract import CLAIM, contract
from validation.warm_finite_producer import execute_slot
from validation.warm_finite_reference import verify_raw


def require_phase():
    from tools.program_state import canonical_digest
    p = json.loads((ROOT/'docs/program/program.json').read_text())
    if next(d for d in p['decisions'] if d['id'] == 'D-PROTOCOL-DIST')['status'] != 'accepted':
        raise ValueError('Finite warm-start protocol is not frozen')
    if next(s for s in p['continuation']['steps'] if s['id'] == 'T1-WARM/PROTOCOL-FREEZE')['state'] != 'complete':
        raise ValueError('Finite warm-start freeze is incomplete')
    eid = p['protocol_phase_bindings'].get('warm-finite')
    row, = [e for e in p['evidence'] if e['id'] == eid]
    path = ROOT/row['path']
    if digest(path) != row['sha256']:
        raise ValueError('Warm freeze binding changed')
    phase = json.loads(path.read_text())
    registry = json.loads((ROOT/'validation/protocols.json').read_text())
    if (phase['kind'] != 'warm_finite_phase_v1' or phase['source_digest'] != source_digest()
            or phase['runtime'] != require_runtime() or phase['contract'] != contract()
            or phase['registry_sha256'] != digest(ROOT/'validation/protocols.json')
            or phase['entry_sha256'] != canonical_digest(registry['entries']['V12'])
            or registry['entries']['V12'].get('contract') != contract()
            or phase['protocol_sha256'] != digest(ROOT/'validation/protocols/v12_protocol.md')
            or phase['resource_authorization'] != 'standing_user_bounded_local_known_answer_execution'):
        raise ValueError('Warm frozen source/runtime/protocol/allocation differs')
    for item in phase['external_files']:
        file = (ROOT/item['path']).resolve()
        if not file.is_relative_to(ROOT) or digest(file) != item['sha256']:
            raise ValueError('Warm supervisor or review changed')
    name = phase['run_name']
    if not isinstance(name,str) or name in {'', '.', '..'} or Path(name).name != name:
        raise ValueError('Unsafe warm run name')
    return {**binding(path), 'run_path':str((ROOT/'validation/artifacts/V12'/name).resolve())}


def campaign(directory):
    directory = Path(directory).resolve()
    phase = require_phase()
    if str(directory) != phase['run_path']:
        raise ValueError('Unallocated warm-start run')
    write_new(directory/'freeze.json', {'phase':phase,'contract':contract(),'source_digest':source_digest()})
    write_new(directory/'generation-start.json', {'created_utc':datetime.now(timezone.utc).isoformat()})
    started = time.monotonic()
    records, error = [], None
    try:
        with bounded_seconds(300):
            for i, slot in enumerate(contract()['slots']):
                write_new(directory/f'slot-{i:02d}-start.json', {'slot':slot})
                raw = execute_slot(slot, directory/f'slot-{i:02d}')
                write_new(directory/f'raw-{i:02d}.json', raw)
                records.append(binding(directory/f'raw-{i:02d}.json'))
    except (Exception, KeyboardInterrupt) as exc:
        error = {'type':type(exc).__name__,'message':str(exc), 'completed_slots':len(records),
                 'partial_work':'retained in physical-updates.jsonl and Store; never retried'}
        write_new(directory/'generation-error.json', error)
    return {'schema_version':1,'validation_id':'V12','claim':CLAIM,'run_dir':str(directory),
        'freeze':binding(directory/'freeze.json'),'records':records,'generation_complete':error is None,
        'generation_error':error,'generation_seconds':time.monotonic()-started}


def reconstruct(result):
    if result.get('claim') != CLAIM or result.get('schema_version') != 1 or result.get('validation_id') != 'V12':
        raise ValueError('Unknown finite warm evidence schema')
    directory = Path(result['run_dir']).resolve()
    phase = require_phase()
    if str(directory) != phase['run_path']:
        raise ValueError('Unallocated warm-start run')
    for i in range(1,4):
        try:
            write_new(directory/f'reconstruction-{i:02d}-start.json', {'created_utc':datetime.now(timezone.utc).isoformat()})
            break
        except FileExistsError:
            pass
    else:
        raise ValueError('Warm reconstruction allocation exhausted')
    try:
        with bounded_seconds(300):
            if read_binding(result['freeze'],directory) != {'phase':phase,'contract':contract(),'source_digest':source_digest()}:
                raise ValueError('Warm evidence freeze differs')
            if result.get('generation_complete') is not True:
                report = {'verdict':'INCONCLUSIVE','complete':False,'reason':'Retained generation is incomplete',
                          'error':result.get('generation_error')}
            else:
                seconds = result['generation_seconds']
                if type(seconds) not in (float,int) or not math.isfinite(seconds) or not 0 <= seconds <= 300:
                    raise ValueError('Warm generation time differs from allocation')
                if len(result['records']) != len(contract()['slots']):
                    raise ValueError('Warm complete roster differs')
                reports=[]
                for index,(slot,item) in enumerate(zip(contract()['slots'],result['records'])):
                    raw=read_binding(item,directory)
                    reports.append(verify_raw(slot,raw,directory/f'slot-{index:02d}'))
                report={'verdict':'PASS','complete':True,'reports':reports,'source_digest':source_digest(),
                        'empirical_speedup_established':False,'distributed_service_accepted':False,
                        'integrated_release_accepted':False}
    except TimeoutError as exc:
        report={'verdict':'INCONCLUSIVE','complete':False,'reason':str(exc)}
    except (ValueError,KeyError,TypeError,IndexError,OSError,AssertionError) as exc:
        report={'verdict':'FAIL','complete':False,'reason':f'{type(exc).__name__}: {exc}'}
    write_new(directory/f'reconstruction-{i:02d}-result.json',report)
    return report
