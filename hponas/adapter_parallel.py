"""Parallel caller-adapter population with ordered durable event batches."""
from copy import copy, deepcopy
import fcntl
import hashlib
import inspect
import math
from pathlib import Path
from statistics import fmean

from hponas.population_adapter import AdapterPopulation, PopulationExecutionError, _digest, _json


class _DeviceAdapter:
    """Pass optional execution context; GPU adapters must explicitly accept it."""
    def __init__(self, adapter, execution):
        self.adapter,self.execution=adapter,execution

    def __getattr__(self, name):
        fn=getattr(self.adapter,name)
        if not callable(fn):return fn
        def invoke(*args,**kwargs):
            if 'execution' in inspect.signature(fn).parameters:
                kwargs['execution']=self.execution
            elif self.execution.gpu_ids and name in {'initialize','restore','train','evaluate','transfer'}:
                raise ValueError('GPU adapter must accept execution context: '+name)
            return fn(*args,**kwargs)
        return invoke


def _perform(task, execution):
    adapter,request,checkpoint=task
    adapter=_DeviceAdapter(adapter,execution)
    from hponas.evaluation import EvaluationContext, EvaluationFold
    context=EvaluationContext(request['role'],EvaluationFold(**request['fold']),request['declaration'])
    operation,config,seed=request['operation'],request['config'],request['seed']
    if operation=='initialize':
        runtime=adapter.initialize(config,seed=seed,evaluation=context)
    elif operation=='transfer':
        payload=adapter.transfer(checkpoint,request['source_config'],config,
            optimizer_policy=request['optimizer_policy'],seed=seed,evaluation=context)
        runtime=adapter.restore(payload,config,seed=seed,evaluation=context)
    else:
        runtime=adapter.restore(checkpoint,config,seed=seed,evaluation=context)
        if operation=='train':adapter.train(runtime,config,evaluation=context)
        elif operation=='evaluate':
            value=adapter.evaluate(runtime,evaluation=context)
            if type(value) not in (int,float) or not math.isfinite(value):
                raise ValueError('Adapter score must be finite')
            return float(value)
    value=_json(adapter.checkpoint(runtime))
    if not isinstance(value,dict):raise ValueError('Adapter checkpoint must be a JSON object')
    restored=adapter.restore(deepcopy(value),deepcopy(config),seed=seed,evaluation=context)
    if _json(adapter.checkpoint(restored))!=value:raise ValueError('Adapter checkpoint does not round-trip')
    return value


class ParallelAdapterPopulation(AdapterPopulation):
    """Same truncation/selection semantics; isolated fold/member tasks per barrier."""
    def __init__(self, *args, executor, **kwargs):
        self.executor=executor
        super().__init__(*args,**kwargs)

    def _read(self):
        # The shared schema has the same ordered replay, but a parallel batch
        # can have a suffix of reserved events. Validate all hashes and ordering.
        import json
        envelope=json.loads(self.path.read_text())
        if set(envelope)!={'payload','sha256'} or _digest(envelope['payload'])!=envelope['sha256']:
            raise ValueError('Population checksum differs')
        state=envelope['payload']
        if (set(state)!={'contract','events','status'} or state['contract']!=self.contract
                or self.adapter.identity!=self.contract['adapter']
                or self.adapter.work_unit!=self.contract['work_unit']
                or state['status'] not in ('tuning','final','complete','failed')):
            raise ValueError('Population contract or state differs')
        seen=set();uncommitted=False
        for event in state['events']:
            if (set(event)!={'key','request','status','result','result_sha256','error'}
                    or not isinstance(event['key'],str) or event['key'] in seen
                    or event['status'] not in ('pending','committed','failed','interrupted')
                    or event['request'].get('operation') not in ('initialize','train','evaluate','transfer','freeze','seal')
                    or event['request'].get('role') not in ('tuning','final')):
                raise ValueError('Malformed parallel adapter event')
            seen.add(event['key'])
            if event['status']=='committed':
                if uncommitted or event['result_sha256']!=_digest(event['result']) or event['error'] is not None:
                    raise ValueError('Invalid parallel committed event order/hash')
            else:
                uncommitted=True
                if event['result'] is not None or event['result_sha256'] is not None:
                    raise ValueError('Uncommitted adapter event contains result')
        if sum(e['request']['operation']=='train' for e in state['events'])>self.contract['max_updates']:
            raise ValueError('Adapter reservations exceed budget')
        if state['status']=='complete' and (uncommitted or not state['events'] or state['events'][-1]['key']!='seal'):
            raise ValueError('Parallel adapter completion lacks final seal')
        return state

    def _batch(self, actions):
        # Build requests with the original method to preserve exact serial keys.
        prepared=[]
        capture=copy(self)
        capture._call=lambda key,request,fn:prepared.append((key,_json(request)))
        for args,kwargs in actions:capture._action(*args,**kwargs)
        values=[];new=[]
        for (key,request),(args,kwargs) in zip(prepared,actions):
            events=self._state['events']
            if self._cursor<len(events):
                event=events[self._cursor]
                if event['key']!=key or event['request']!=request:
                    raise ValueError('Parallel adapter request differs from replay')
                if event['status']!='committed':
                    for pending in events[self._cursor:]:
                        if pending['status']=='pending':pending.update(status='interrupted',error='Lost parallel call; reserved work uncertain')
                    self._state['status']='failed';self._write(self._state)
                    raise PopulationExecutionError('Lost parallel adapter batch')
                values.append(deepcopy(event['result']))
            else:
                if request['operation']=='train' and sum(e['request']['operation']=='train' for e in events)>=self.contract['max_updates']:
                    raise ValueError('Adapter update budget exhausted')
                if self._state['status'] in ('complete','failed'):
                    raise ValueError('Terminal adapter has missing events')
                event=dict(key=key,request=request,status='pending',result=None,result_sha256=None,error=None)
                events.append(event);values.append(None)
                checkpoint=args[6] if len(args)>6 else kwargs.get('checkpoint')
                new.append((len(values)-1,event,(self.adapter,request,deepcopy(checkpoint))))
            self._cursor+=1
        if not new:return values
        self._write(self._state)
        try:
            results=self.executor.map(_perform,[row[2] for row in new])
        except BaseException as exc:
            for _,event,_ in new:event.update(status='failed',error=type(exc).__name__+': '+str(exc))
            self._state['status']='failed';self._write(self._state)
            if isinstance(exc,Exception):raise PopulationExecutionError(str(exc)) from exc
            raise
        for (index,event,_),result in zip(new,results):
            result=_json(result);event.update(status='committed',result=result,result_sha256=_digest(result))
            values[index]=deepcopy(result)
            self._write(self._state)
        return values

    def run(self):
        with Path(str(self.path)+'.coordinator.lock').open('a') as lease:
            fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._state,self._cursor=self._read(),0
            try:self._execute_parallel()
            except PopulationExecutionError:return self._report(self._state)
            if self._cursor!=len(self._state['events']):raise ValueError('Unexpected trailing adapter events')
            self._state['status']='complete';self._write(self._state)
            return self._report(self._state)

    def _execute_parallel(self):
        tuning=self._replicas('tuning')
        members={name:dict(config=deepcopy(config),checkpoints=[],schedule=[],policy='INITIAL')
                 for name,config in sorted(self.contract['members'].items())}
        actions=[((f'init:{name}:{i}','initialize',name,m['config'],context,seed),{})
                 for name,m in members.items() for i,(context,seed) in enumerate(tuning)]
        values=iter(self._batch(actions))
        for m in members.values():m['checkpoints']=[next(values) for _ in tuning]
        for block in range(self.contract['rounds']):
            for step in range(self.contract['updates']):
                actions=[((f'train:{block}:{name}:{i}:{step}','train',name,m['config'],context,seed,m['checkpoints'][i]),{})
                         for name,m in members.items() for i,(context,seed) in enumerate(tuning)]
                values=iter(self._batch(actions))
                for m in members.values():m['checkpoints']=[next(values) for _ in tuning]
            actions=[((f'score:{block}:{name}:{i}','evaluate',name,m['config'],context,seed,m['checkpoints'][i]),{})
                     for name,m in members.items() for i,(context,seed) in enumerate(tuning)]
            values=iter(self._batch(actions));scores={name:fmean(next(values) for _ in tuning) for name in members}
            for m in members.values():
                m['schedule'].append(dict(config=deepcopy(m['config']),updates=self.contract['updates'],optimizer_policy=m['policy']))
                m['policy']='KEEP'
            sign=1 if self.declaration.objectives[0].direction=='min' else -1
            ranking=sorted(members,key=lambda name:(sign*scores[name],name))
            if block==self.contract['rounds']-1:break
            parent,child=ranking[0],ranking[-1];teacher=members[parent]
            index=int.from_bytes(hashlib.sha256(f"{self.contract['seed']}:{block}".encode()).digest()[:8],'big')%len(self.contract['exploration'])
            config=deepcopy(self.contract['exploration'][index])
            actions=[((f'transfer:{block}:{child}:{i}','transfer',child,config,context,seed,teacher['checkpoints'][i]),
                dict(source_config=teacher['config'],parent=parent,optimizer_policy=self.contract['optimizer_policy'])) for i,(context,seed) in enumerate(tuning)]
            members[child].update(config=config,checkpoints=self._batch(actions),schedule=deepcopy(teacher['schedule']),policy=self.contract['optimizer_policy'])
        winner=ranking[0];frozen=dict(member=winner,schedule=members[winner]['schedule'],tuning_mean=scores[winner])
        frozen=self._call('freeze',dict(operation='freeze',role='tuning',scores=scores,schedules={n:m['schedule'] for n,m in members.items()}),lambda:frozen)
        final=self._replicas('final');config=frozen['schedule'][0]['config']
        checkpoints=self._batch([((f'final:init:{i}','initialize',winner,config,context,seed),{}) for i,(context,seed) in enumerate(final)])
        for block,row in enumerate(frozen['schedule']):
            if block and row['optimizer_policy']!='KEEP':
                checkpoints=self._batch([((f'final:transfer:{i}:{block}','transfer',winner,row['config'],context,seed,checkpoints[i]),
                    dict(source_config=config,parent='frozen_schedule',optimizer_policy=row['optimizer_policy'])) for i,(context,seed) in enumerate(final)])
            config=row['config']
            for step in range(row['updates']):
                checkpoints=self._batch([((f'final:train:{i}:{block}:{step}','train',winner,config,context,seed,checkpoints[i]),{}) for i,(context,seed) in enumerate(final)])
        scores=self._batch([((f'final:score:{i}','evaluate',winner,config,context,seed,checkpoints[i]),{}) for i,(context,seed) in enumerate(final)])
        sealed=dict(final_records=scores,final_mean=fmean(scores))
        if self._call('seal',dict(operation='seal',role='final',selection_sha256=_digest(frozen),final_records=scores),lambda:sealed)!=sealed:
            raise ValueError('Parallel final seal differs')
