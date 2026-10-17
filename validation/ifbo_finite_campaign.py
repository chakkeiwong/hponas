"""Once-only externally bound ifBO feasibility and independently checked data."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

import numpy as np
from validation.evidence import ROOT, digest, source_digest
from validation.ifbo_finite_contract import CLAIM, contract
from validation.ifbo_finite_reference import verify_case
from validation.population_campaign import write_new, binding, read_binding
from validation.stylized_campaign import bounded_seconds
from validation.tier1_campaign import require_runtime, first_difference


def runtime():
    value=require_runtime()
    sys.path.insert(0,str(ROOT/'.hponas-runtime/ifbo-reference-deps'))
    value['reference_packages']={name:importlib.metadata.version(name) for name in ['pandas','submitit']}
    return value


def require_phase():
    from tools.program_state import canonical_digest
    program=json.loads((ROOT/'docs/program/program.json').read_text())
    if next(d for d in program['decisions'] if d['id']=='D-PROTOCOL-T3-FEASIBILITY')['status']!='accepted':
        raise ValueError('ifBO feasibility decision is not frozen')
    if next(s for s in program['continuation']['steps'] if s['id']=='T3-01/FEASIBILITY-FREEZE')['state']!='complete':
        raise ValueError('ifBO feasibility stage is not frozen')
    eid=program['protocol_phase_bindings'].get('tier3-feasibility')
    rows=[e for e in program['evidence'] if e['id']==eid]
    if len(rows)!=1:raise ValueError('ifBO phase binding missing')
    path=ROOT/rows[0]['path']
    if digest(path)!=rows[0]['sha256']:raise ValueError('ifBO phase changed')
    phase=json.loads(path.read_text())
    registry=json.loads((ROOT/'validation/protocols.json').read_text())
    if (phase.get('kind')!='ifbo_finite_phase_v1' or phase.get('source_digest')!=source_digest()
        or phase.get('runtime')!=runtime() or phase.get('contract')!=contract()
        or phase.get('registry_sha256')!=digest(ROOT/'validation/protocols.json')
        or phase.get('registry_entry_sha256')!=canonical_digest(registry['entries']['V15a'])
        or registry['entries']['V15a'].get('contract')!=contract()
        or phase.get('protocol_sha256')!=digest(ROOT/'validation/protocols/v15a_protocol.md')
        or phase.get('resource_authorization')!='standing_user_bounded_local_known_answer_execution'):
        raise ValueError('ifBO source/runtime/protocol/allocation differs')
    for item in phase['external_files']:
        file=(ROOT/item['path']).resolve()
        if not file.is_relative_to(ROOT) or digest(file)!=item['sha256']:
            raise ValueError('ifBO external reference/harness changed')
    run=phase.get('run_name')
    if not isinstance(run,str) or Path(run).name!=run or run in {'','.', '..'}:
        raise ValueError('Invalid ifBO allocated run')
    return {**binding(path),'run_path':str((ROOT/'validation/artifacts/V15a'/run).resolve()),
            'harness':str((ROOT/phase['harness']).resolve())}


def require_run(directory):
    phase=require_phase()
    if str(Path(directory).resolve())!=phase['run_path']:raise ValueError('ifBO run differs from allocation')
    return phase


def producer(phase):
    sys.path.insert(0,str(Path(phase['harness']).parent))
    module=importlib.import_module('finite_reference_run')
    if Path(module.__file__).resolve()!=Path(phase['harness']):
        raise ValueError('Wrong reference harness imported')
    return module


def campaign(directory):
    directory=Path(directory).resolve();phase=require_run(directory)
    write_new(directory/'ifbo-freeze.json',{'contract':contract(),'source_digest':source_digest(),
        'runtime':runtime(),'phase':phase})
    write_new(directory/'generation-start.json',{'created_utc':datetime.now(timezone.utc).isoformat()})
    module=producer(phase);model=module.load_model()
    records=[];started=time.monotonic()
    with (directory/'journal.jsonl').open('x') as journal:
        def event(value):
            journal.write(json.dumps(value)+'\n');journal.flush();os.fsync(journal.fileno())
        with bounded_seconds(300):
            for index,slot in enumerate(contract()['slots']):
                event({'action':'start','index':index,'slot':slot})
                record={'slot':slot,'status':'incomplete','error':None,'raw':None}
                try:
                    raw=module.execute_case(slot,directory/f'case-{index:02d}',model)
                    path=directory/f'raw-{index:02d}.json';write_new(path,raw)
                    record.update(status='complete',raw=binding(path))
                except Exception as exc:
                    record['error']=f'{type(exc).__name__}: {exc}'
                records.append(record)
                path=directory/f'receipt-{index:02d}.json';write_new(path,record)
                event({'action':'end','index':index,'receipt':binding(path)})
    write_new(directory/'slots.json',records)
    return {'schema_version':1,'validation_id':'V15a','claim':CLAIM,'run_dir':str(directory),
            'freeze':binding(directory/'ifbo-freeze.json'),'slots':binding(directory/'slots.json'),
            'journal':binding(directory/'journal.jsonl'),'generation_seconds':time.monotonic()-started}


def consume(directory):
    for index in range(1,4):
        try:
            write_new(directory/f'reconstruction-{index:02d}-start.json',{
                'created_utc':datetime.now(timezone.utc).isoformat(),'source_digest':source_digest()})
            return index
        except FileExistsError:continue
    raise ValueError('ifBO reconstruction allocation exhausted')


def replay_equal(raw,replay,original_dir,replay_dir):
    left,right=deepcopy(raw),deepcopy(replay)
    for value in (left,right):
        value['ifbo'].pop('optimization_seconds')
        for row in value['ifbo']['trace']:
            row.pop('tensors',None)
    difference=first_difference(left,right)
    if difference:raise ValueError('Pretrained scheduler identity replay differs at '+difference)
    names={row['tensors']['path'] for row in raw['ifbo']['trace'] if 'tensors' in row}
    if {p.name for p in Path(original_dir).iterdir()}!=names:
        raise ValueError('Raw pretrained tensor inventory differs')
    for name in names:
        with np.load(Path(original_dir)/name,allow_pickle=False) as a,np.load(Path(replay_dir)/name,allow_pickle=False) as b:
            if set(a.files)!=set(b.files) or any(not np.array_equal(a[k],b[k]) for k in a.files):
                raise ValueError('Pretrained model/token tensor replay differs')


def _reconstruct(result,directory):
    phase=require_run(directory)
    expected={'contract':contract(),'source_digest':source_digest(),'runtime':runtime(),'phase':phase}
    if read_binding(result['freeze'],directory)!=expected:raise ValueError('ifBO run freeze differs')
    records=read_binding(result['slots'],directory)
    if [r['slot'] for r in records]!=contract()['slots']:raise ValueError('ifBO fixed roster differs')
    path=Path(result['journal']['path']).resolve()
    if not path.is_relative_to(directory) or digest(path)!=result['journal']['sha256']:raise ValueError('ifBO journal changed')
    journal=[json.loads(line) for line in path.read_text().splitlines()]
    if len(journal)!=2*len(records):raise ValueError('ifBO journal coverage differs')
    duration=result['generation_seconds']
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<0:raise ValueError('Invalid duration')
    incomplete=duration>300;reports=[]
    module=producer(phase);model=module.load_model()
    for index,record in enumerate(records):
        if journal[2*index]!={'action':'start','index':index,'slot':record['slot']}:
            raise ValueError('ifBO case start differs')
        end=journal[2*index+1]
        if end['action']!='end' or end['index']!=index or read_binding(end['receipt'],directory)!=record:
            raise ValueError('ifBO case end differs')
        if record['status']!='complete':incomplete=True;continue
        if record['error'] is not None:raise ValueError('Complete case has error')
        raw=read_binding(record['raw'],directory)
        if raw['slot']!=record['slot']:raise ValueError('ifBO raw slot differs')
        data_dir=directory/f'case-{index:02d}'
        report=verify_case(raw,data_dir)
        with tempfile.TemporaryDirectory(prefix='ifbo-reference-replay-') as temp:
            replay_dir=Path(temp)/'case'
            replay=module.execute_case(record['slot'],replay_dir,model)
            replay_equal(raw,replay,data_dir,replay_dir)
        reports.append(report)
    return {'verdict':'INCONCLUSIVE' if incomplete else 'PASS' if all(r['passes'] for r in reports) else 'FAIL',
            'reports':reports,'complete':not incomplete,'identity_verified':not incomplete,
            'scope':'fixed_finite_reference_feasibility_only','integrated_release_accepted':False}


def reconstruct(result):
    if result.get('schema_version')!=1 or result.get('claim')!=CLAIM or result.get('validation_id')!='V15a':
        raise ValueError('Unknown ifBO finite schema')
    directory=Path(result['run_dir']).resolve();require_run(directory);index=consume(directory)
    try:
        with bounded_seconds(300):report=_reconstruct(result,directory)
    except TimeoutError as exc:
        report={'verdict':'INCONCLUSIVE','reason':str(exc),'complete':False,'identity_verified':False}
    except (ValueError,KeyError,TypeError,IndexError,OSError) as exc:
        report={'verdict':'FAIL','reason':f'{type(exc).__name__}: {exc}','complete':False,'identity_verified':False}
    write_new(directory/f'reconstruction-{index:02d}-result.json',report)
    return report


def recompute_result(result):
    return reconstruct(result)['verdict']
