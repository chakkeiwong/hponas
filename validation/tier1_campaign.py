"""Immutable finite Tier-1 evidence and independently reconstructed decisions."""
from copy import deepcopy
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import tempfile
import time

from validation.evidence import ROOT, digest, source_digest
from validation.tier1_contract import CLAIM, contract
from validation.tier1_producers import execute_slot, write_new
from validation.tier1_reference import verify_slot
from validation.stylized_campaign import bounded_seconds


def runtime():
    return {'python': platform.python_version(), 'machine': platform.machine(),
            'packages': {name: importlib.metadata.version(name) for name in
                         ['numpy','scipy','torch','botorch','gpytorch','optuna','cloudpickle']},
            'threads': {name: os.environ.get(name) for name in
                        ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},
            'cpu_affinity_count': len(os.sched_getaffinity(0)),
            'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES')}


def require_runtime():
    value=runtime()
    if (value['cpu_affinity_count']!=1 or set(value['threads'].values())!={'1'}
            or value['cuda_visible_devices']!=''):
        raise ValueError('Finite Tier-1 requires one CPU affinity, single numerical threads and no GPU')
    return value


def binding(path):
    return {'path':str(Path(path).resolve()),'sha256':digest(path)}


def read_binding(item, directory):
    path=Path(item['path']).resolve()
    if not path.is_relative_to(directory) or digest(path)!=item['sha256']:
        raise ValueError('Changed or external finite Tier-1 artifact')
    return json.loads(path.read_text())


def projection(spec, raw):
    """Compare scientific/method state; measured durations are never replayed.

Vector Result.cost is elapsed time; its separately recorded integer work is the
decision quantity and remains in this projection. Timing validity is checked
separately, including the resource report tuning_elapsed_seconds field.
Resource limits, counts and physical work remain compared. Trust state
checksums depend on that timing metadata; their payloads
are compared in full after removing timing.
"""
    kind=spec['kind']
    if kind in {'trust','priorband'}:
        fields=['summary','updates']
        row={k:raw[k] for k in fields}
        row['method_state']=raw['snapshot']['searcher_state']
        row['scheduler_state']=raw['snapshot']['scheduler_state']
        if kind=='trust':
            row['boundary']=raw['recovery_boundary']['searcher_state'] if raw['recovery_boundary'] else None
        else:
            row['endpoints']=raw['endpoints']
    elif kind=='vector':
        row={'observations':raw['observations'],'method_state':raw['snapshot']['searcher_state']}
    else:
        row=raw
    def clean(value):
        if isinstance(value,list):
            return [clean(v) for v in value]
        if not isinstance(value,dict):
            return value
        excluded={'timestamp','elapsed_seconds','total_elapsed_seconds','duration_seconds','wall_time','wall_seconds','tuning_elapsed_seconds'}
        if kind=='trust':
            excluded.add('sha256')
        if kind=='vector':
            excluded.update({'cost','total_cost'})
        return {k:clean(v) for k,v in value.items() if k not in excluded}
    return clean(json.loads(json.dumps(row, allow_nan=False)))


def replay_slot(spec, raw):
    if spec['kind']=='cost':
        from validation.cost_replay import replay_run
        return replay_run(raw)['status']
    # Finite full regeneration is deliberately labelled production identity
    # replay. It cannot replace the independent mathematical reference above.
    with tempfile.TemporaryDirectory(prefix='tier1-identity-') as temporary:
        actual=execute_slot(spec,Path(temporary)/'slot')
    difference=first_difference(projection(spec,actual),projection(spec,raw))
    if difference:
        raise ValueError('Production method/seed/options/recovery replay differs at '+difference)
    return 'PASS'


def first_difference(left,right,path='raw'):
    if isinstance(left,dict) and isinstance(right,dict) and set(left)==set(right):
        return next((d for k in left if (d:=first_difference(left[k],right[k],path+'.'+str(k)))),None)
    if isinstance(left,list) and isinstance(right,list) and len(left)==len(right):
        return next((d for i,(a,b) in enumerate(zip(left,right)) if (d:=first_difference(a,b,path+f'[{i}]'))),None)
    return None if left==right else path


def campaign(entry, run_dir):
    run_dir=Path(run_dir).resolve()
    spec=contract(entry)
    phase=require_phase(entry)
    require_run(entry,run_dir)
    freeze={'contract':spec,'source_digest':source_digest(),'runtime':require_runtime(),
            'protocol_sha256':digest(ROOT/'validation/protocols'/f"{entry.lower().replace('-','_')}_protocol.md"),
            'registry_sha256':digest(ROOT/'validation/protocols.json'),'run_dir':str(run_dir),
            'phase':phase}
    write_new(run_dir/'tier1-freeze.json',freeze)
    records=[]
    exhausted=False
    started=time.monotonic()
    with (run_dir/'slot-journal.jsonl').open('x') as journal:
        def event(row):
            journal.write(json.dumps(row,allow_nan=False)+'\n'); journal.flush(); os.fsync(journal.fileno())
        with bounded_seconds(spec['wall_seconds_per_process']):
            for index,slot in enumerate(spec['slots']):
                item={'slot':slot,'status':'incomplete','raw':None,'error':None}
                event({'action':'start','index':index,'slot':slot})
                if exhausted:
                    item['error']='prior_interruption_or_process_deadline'
                else:
                    try:
                        raw=execute_slot(slot,run_dir/f'slot-{index:03d}')
                        path=run_dir/f'raw-{index:03d}.json'
                        write_new(path,raw)
                        item.update(status='complete',raw=binding(path))
                    except Exception as exc:
                        item['error']=f'{type(exc).__name__}: {exc}'
                        exhausted=isinstance(exc,TimeoutError)
                        # Slot starts and any physical/checkpoint files survive;
                        # unknown partial work never becomes a zero-cost success.
                records.append(item)
                write_new(run_dir/f'slot-receipt-{index:03d}.json',item)
                event({'action':'end','index':index,'receipt':binding(run_dir/f'slot-receipt-{index:03d}.json')})
    write_new(run_dir/'slots.json',records)
    return {'schema_version':1,'validation_id':entry,'claim':CLAIM,'run_dir':str(run_dir),
            'freeze':binding(run_dir/'tier1-freeze.json'),'slots':binding(run_dir/'slots.json'),
            'journal':binding(run_dir/'slot-journal.jsonl'),'generation_seconds':time.monotonic()-started}


def reconstruct(entry,result,*,replay=True):
    if result.get('validation_id')!=entry or result.get('claim')!=CLAIM or result.get('schema_version')!=1:
        raise ValueError('Unknown finite Tier-1 result identity')
    directory=Path(result['run_dir']).resolve()
    require_run(entry,directory)
    freeze=read_binding(result['freeze'],directory)
    spec=contract(entry)
    if (freeze['contract']!=spec or freeze['source_digest']!=source_digest()
            or freeze['runtime']!=require_runtime() or freeze['run_dir']!=str(directory)
            or freeze['phase']!=require_phase(entry)
            or freeze['registry_sha256']!=digest(ROOT/'validation/protocols.json')
            or freeze['protocol_sha256']!=digest(ROOT/'validation/protocols'/f"{entry.lower().replace('-','_')}_protocol.md")):
        raise ValueError('Finite Tier-1 freeze/source/runtime differs')
    seconds=result['generation_seconds']
    if type(seconds) not in (float,int) or not math.isfinite(seconds) or seconds<0:
        raise ValueError('Invalid generation duration')
    records=read_binding(result['slots'],directory)
    if [r['slot'] for r in records]!=spec['slots']:
        raise ValueError('Finite Tier-1 ordered unique roster differs')
    journal_path=Path(result['journal']['path']).resolve()
    if not journal_path.is_relative_to(directory) or digest(journal_path)!=result['journal']['sha256']:
        raise ValueError('Changed slot journal')
    journal=[json.loads(line) for line in journal_path.read_text().splitlines()]
    if len(journal)!=2*len(records):
        raise ValueError('Missing incremental slot events')
    for index,(slot,record) in enumerate(zip(spec['slots'],records)):
        if journal[2*index]!={'action':'start','index':index,'slot':slot}:
            raise ValueError('Slot start identity differs')
        end=journal[2*index+1]
        if end['action']!='end' or end['index']!=index or read_binding(end['receipt'],directory)!=record:
            raise ValueError('Slot end identity differs')
    incomplete=seconds>spec['wall_seconds_per_process']
    summaries=[]
    with bounded_seconds(spec['wall_seconds_per_process']):
        for record in records:
            if record['status']=='incomplete':
                if not record['error']:
                    raise ValueError('Incomplete slot missing retained reason')
                incomplete=True
                continue
            if record['status']!='complete' or record['error'] is not None:
                raise ValueError('Unknown slot disposition')
            raw=read_binding(record['raw'],directory)
            try:
                validate_timings(raw)
                report=verify_slot(record['slot'],raw)
                if report.get('status')=='INCONCLUSIVE':
                    incomplete=True
                elif replay and replay_slot(record['slot'],raw)!='PASS':
                    incomplete=True
            except TimeoutError:
                return {'verdict':'INCONCLUSIVE','reason':'reconstruction_deadline',
                        'method_identity_verified':False,'default_activation':False}
            except (ValueError,KeyError,TypeError,IndexError) as exc:
                return {'verdict':'FAIL','reason':str(exc),'slot':record['slot']['id'],
                        'method_identity_verified':False,'default_activation':False}
            summaries.append({'slot':record['slot']['id'],'reference':report})
    return {'verdict':'INCONCLUSIVE' if incomplete else 'PASS','summaries':summaries,
            'method_identity_verified':replay and not incomplete,
            'scope':'exposed_finite_conformance_only','default_activation':False}


def recompute_result(entry,result):
    return reconstruct(entry,result)['verdict']


def validate_timings(value):
    if isinstance(value,list):
        for row in value:
            validate_timings(row)
    elif isinstance(value,dict):
        for key,row in value.items():
            if key in {'elapsed_seconds','total_elapsed_seconds','duration_seconds','wall_time','wall_seconds','tuning_elapsed_seconds'}:
                if type(row) not in (int,float) or not math.isfinite(row) or row<0:
                    raise ValueError('Nonfinite or negative measured timing')
            else:
                validate_timings(row)


def require_phase(entry):
    """Preparation cannot silently launch official campaigns on a draft phase."""
    from validation.tier1_contract import ENTRIES
    from tools.program_state import canonical_digest
    program=json.loads((ROOT/'docs/program/program.json').read_text())
    decisions={d['id']:d['status'] for d in program.get('decisions',[])}
    stages={s['id']:s['state'] for s in program.get('continuation',{}).get('steps',[])}
    if (decisions.get('D-PROTOCOL-T1')!='accepted'
            or stages.get('T1-GATE/PROTOCOL-FREEZE')!='complete'):
        raise ValueError('Tier-1 phase is not frozen; exact protocol closure is incomplete')
    ident=program.get('protocol_phase_bindings',{}).get('tier1')
    candidates=[e for e in program['evidence'] if e['id']==ident]
    if len(candidates)!=1:
        raise ValueError('Tier-1 phase is not frozen; preparation cannot launch campaigns')
    item=candidates[0]; path=ROOT/item['path']
    if digest(path)!=item['sha256']:
        raise ValueError('Changed Tier-1 phase binding')
    phase=json.loads(path.read_text())
    registry=json.loads((ROOT/'validation/protocols.json').read_text())
    if (phase.get('kind')!='tier1_finite_phase_v1' or phase.get('source_digest')!=source_digest()
            or phase.get('registry_sha256')!=digest(ROOT/'validation/protocols.json')
            or phase.get('runtime')!=require_runtime() or set(phase.get('entries',{}))!=set(ENTRIES)
            or phase.get('resource_authorization')!='standing_user_bounded_local_known_answer_execution'):
        raise ValueError('Tier-1 phase source/runtime/roster/allocation differs')
    for vid in ENTRIES:
        expected={'contract':contract(vid),'registry_entry_sha256':canonical_digest(registry['entries'][vid]),
                  'protocol_sha256':digest(ROOT/'validation/protocols'/f"{vid.lower().replace('-','_')}_protocol.md")}
        if phase['entries'][vid]!=expected:
            raise ValueError('Tier-1 exact entry freeze differs: '+vid)
    if set(phase.get('run_names',{}))!=set(ENTRIES):
        raise ValueError('Exact once-only run allocation required')
    for name in phase['run_names'].values():
        if not isinstance(name,str) or not name or Path(name).name!=name or name in {'.','..'}:
            raise ValueError('Unsafe run allocation')
    return {'path':str(path.resolve()),'sha256':item['sha256'],
            'run_path':str((ROOT/'validation/artifacts'/entry/phase['run_names'][entry]).resolve())}


def require_run(entry,directory):
    if Path(directory).resolve()!=Path(require_phase(entry)['run_path']):
        raise ValueError('Run directory differs from frozen once-only allocation')
