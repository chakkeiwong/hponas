"""Single-coordinator population batches; workers never write shared journals."""
from contextlib import nullcontext
from copy import deepcopy
import fcntl
import json
from pathlib import Path

from hponas.persistence import atomic_json
from hponas.population import PopulationCheckpoint, _digest


def journal_path(path):
    return Path(str(path)+'.parallel.json')


def read_journal(path):
    path=journal_path(path)
    if not path.exists():return None
    envelope=json.loads(path.read_text())
    if set(envelope)!={'payload','sha256'} or _digest(envelope['payload'])!=envelope['sha256']:
        raise ValueError('Parallel population journal checksum differs')
    value=envelope['payload']
    if (value.get('status') not in {'pending','computed','committed','failed','interrupted'}
            or value.get('id')!=_digest(value.get('requests'))
            or type(value.get('reserved_updates')) is not int or value['reserved_updates']<0):
        raise ValueError('Malformed parallel reservation')
    if value['status'] in {'computed','committed'} and (not isinstance(value.get('after'),dict)
            or not isinstance(value.get('results'),list) or len(value['results'])!=len(value['requests'])):
        raise ValueError('Incomplete computed population batch')
    return value


def write_journal(path, value):
    atomic_json(journal_path(path),{'payload':value,'sha256':_digest(value)})


def guard_serial(path):
    journal=read_journal(path)
    if journal and journal['status']!='committed':
        raise ValueError('Parallel population reservation must be resolved before serial mutation')


def uncertain_work(path):
    journal=read_journal(path)
    if journal and journal['status']=='computed':
        envelope=json.loads(Path(path).read_text())
        return 0 if _digest(envelope['payload'])==_digest(journal['after']) else journal['reserved_updates']
    return journal['reserved_updates'] if journal and journal['status'] in {'pending','failed','interrupted'} else 0


class _MemoryPopulation(PopulationCheckpoint):
    def __init__(self, objective, snapshot, device):
        self.objective,self.identity,self.state,self.device=objective,objective.identity,deepcopy(snapshot),device
        self.path=None

    def _lock(self):return nullcontext()
    def _read(self):return deepcopy(self.state)
    def _write(self,state):self.state=deepcopy(state)


def _compute(task, execution):
    objective,snapshot,request=task
    store=_MemoryPopulation(objective,snapshot,execution.device)
    event=store.exploit(**request)
    return event


def run_batch(population, requests, executor):
    """Execute disjoint children from one frozen snapshot, then commit atomically.

    Unknown worker outcomes are terminal and charged at the full reservation.
    A fully computed batch can recover before/after the atomic population write.
    """
    if not requests:return []
    requests=deepcopy(list(requests))
    ids=[r['event_id'] for r in requests];children=[r['child'] for r in requests]
    if len(set(ids))!=len(ids) or len(set(children))!=len(children):
        raise ValueError('Parallel batch requires unique events and target members')
    if any(r['parent'] in children and r['parent']!=r['child'] for r in requests):
        raise ValueError('Dependent parent/child updates require a barrier')
    path=population.path
    with Path(str(path)+'.parallel.lock').open('a') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with population._lock():
            snapshot=population._read()
            existing=read_journal(path)
            batch_id=_digest(requests)
            if existing and existing['id']==batch_id:
                journal=existing
                if journal['status']=='committed':
                    if any(snapshot['events'].get(r['event_id'])!=e for r,e in zip(requests,journal['results'])):
                        raise ValueError('Committed parallel journal differs from population')
                    return deepcopy(journal['results'])
                if journal['status']=='pending':
                    journal.update(status='interrupted',error='Lost batch; full reserved work remains uncertain')
                    write_journal(path,journal)
                    raise RuntimeError(journal['error'])
                if journal['status'] in {'failed','interrupted'}:
                    raise RuntimeError(journal['error'])
            else:
                if existing and existing['status']!='committed':
                    raise ValueError('Resolve the preceding parallel reservation')
                complete=[snapshot['events'].get(i) for i in ids]
                if all(e and e['status']=='committed' for e in complete):
                    for e,r in zip(complete,requests):
                        for k,v in r.items():
                            if k not in {'event_id','advance_to'} and e['request'].get(k)!=v:
                                raise ValueError('Parallel event identity reused')
                    return deepcopy(complete)
                reserved=0
                for request in requests:
                    if request['parent'] not in snapshot['members'] or request['child'] not in snapshot['members']:
                        raise ValueError('Unknown parallel population member')
                    old=snapshot['events'].get(request['event_id'])
                    target=request.get('advance_to',len(request.get('weights',())))
                    if target is None:target=len(request.get('weights',()))
                    if type(target) is not int or not 0<=target<=len(request.get('weights',())):
                        raise ValueError('Invalid parallel update target')
                    # Validate with the serial request parser without executing
                    # any numerical update or consuming a durable reservation.
                    memory=_MemoryPopulation(population.objective,snapshot,'cpu')
                    memory.exploit(**{**request,'advance_to':old['completed_updates'] if old else 0})
                    reserved+=target-(old['completed_updates'] if old else 0)
                used=sum(e['completed_updates']+int(e['inflight']) for e in snapshot['events'].values())
                if reserved<0 or used+reserved>snapshot['max_updates']:
                    raise ValueError('Parallel batch exceeds remaining update budget')
                journal={'id':batch_id,'requests':requests,'before':_digest(snapshot),'status':'pending',
                         'reserved_updates':reserved,'results':None,'after':None}
                write_journal(path,journal)
        if journal['status']=='pending':
            try:
                results=executor.map(_compute,[(population.objective,snapshot,r) for r in requests])
                if len(results)!=len(requests):raise ValueError('Incomplete population result batch')
                if any(e['status'] not in {'pending','committed'} for e in results):
                    raise RuntimeError('Population worker failed; full batch work is uncertain')
                after=deepcopy(snapshot)
                for request,event in zip(requests,results):
                    after['events'][request['event_id']]=event
                    if event['status']=='committed':
                        after['members'][request['child']]=deepcopy(event['candidate'])
                after['lineage']=[{'event':ident,'parent':e['request']['parent'],'child':e['request']['child'],
                    'teacher_sha256':e['teacher_sha256'],'result_sha256':e['result_sha256']}
                    for ident,e in after['events'].items() if e['status']=='committed']
                journal.update(status='computed',results=results,after=after)
                write_journal(path,journal)
            except BaseException as exc:
                # If the computed journal was atomically stored, preserve it.
                durable=read_journal(path)
                if durable['status']=='pending':
                    durable.update(status='failed',error=type(exc).__name__+': '+str(exc));write_journal(path,durable)
                raise
        with population._lock():
            current=population._read()
            if _digest(current) not in {journal['before'],_digest(journal['after'])}:
                raise ValueError('Stale population batch commit refused')
            if _digest(current)==journal['before']:
                # Validate against the same original replay logic before write.
                envelope={'payload':journal['after'],'sha256':_digest(journal['after'])}
                # Validation is performed by a memory-backed facade without
                # exposing any mutation to the on-disk population.
                class MemoryPath:
                    def read_text(self):return json.dumps(envelope)
                validator=object.__new__(PopulationCheckpoint)
                validator.path=MemoryPath();validator.objective=population.objective;validator.identity=population.identity
                validator._read()
                population._write(journal['after'])
                population._read()  # validate full original lineage replay
            journal['status']='committed';write_journal(path,journal)
        return deepcopy(journal['results'])


def train_batch(population, event_prefix, updates, executor):
    snapshot=population.snapshot()
    requests=[]
    for name,member in sorted(snapshot['members'].items()):
        eid=event_prefix+name
        old=snapshot['events'].get(eid)
        options=old['request'] if old else member
        requests.append(dict(event_id=eid,parent=name,child=name,architecture=options['architecture'],
            optimizer=options['optimizer'],mode='TRAIN',optimizer_policy='COPY',weights=[0]*updates,seed=0))
    return run_batch(population,requests,executor)
