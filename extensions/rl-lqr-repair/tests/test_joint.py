from copy import deepcopy
from pathlib import Path
import json
import pytest
from hponas_rl_lqr_repair import joint
from hponas_rl_lqr_repair.experiments import BASE,ROOT,read

class FakeMember:
    def __init__(self,config,seed,method='plain'):
        self.config=deepcopy(config);self.seed=seed;self.method=method
        self.transitions=0;self.updates=0;self.value=10.+seed%3
    def state(self):return deepcopy(self.__dict__)
    @classmethod
    def restore(cls,state):
        m=cls(state['config'],state['seed'],state['method']);m.__dict__.update(deepcopy(state));return m
    @staticmethod
    def identity(state):return json.dumps(state,sort_keys=True)
    def train(self,n,extra_updates=0):
        self.updates+=(max(0,self.transitions+n-256)//4-max(0,self.transitions-256)//4)+extra_updates
        self.transitions+=n;self.value*=.9
    def compatible_copy(self,config,seed):
        m=self.restore(self.state());m.config=deepcopy(config);m.seed=seed;return m
    def save(self,path):Path(path).write_text(json.dumps(self.state()))

class FakeExplorer:
    def __init__(self,seed):pass
    def observe(self,*args):pass
    def finish_round(self,*args):pass
    def propose(self,config,*args,architecture=False,count=1):
        return [dict(config,actor_hiddens=[16,16],critic_hiddens=[16,16]) if architecture else dict(config) for _ in range(count)],dict(test=True)

@pytest.mark.parametrize('label',['repaired_bgpbt','plain_bgpbt','repaired_static'])
def test_complete_scheduler_rejects_bad_children_and_matches_work(tmp_path,monkeypatch,label):
    monkeypatch.setattr(joint,'SACMember',FakeMember);monkeypatch.setattr(joint,'JointExplorer',FakeExplorer)
    monkeypatch.setattr(joint,'evaluate',lambda m:dict(cost=m.value))
    monkeypatch.setattr(joint,'binding',lambda p:dict(path=str(p)))
    def bad_transfer(donor,config,seed,steps,adapt_steps):
        m=FakeMember.restore(donor.state());m.config=config;m.value=100.
        return m,dict(teacher_unchanged=True)
    monkeypatch.setattr(joint,'distill',bad_transfer)
    result=joint.procedure((label,10821,str(tmp_path/'case')))
    assert result['work']['transitions']==20480
    assert result['work']['gradient_components']==20992
    if label!='repaired_static':
        architecture=[e for e in result['events'] if e['kind']=='architecture']
        assert len(architecture)==2 and not any(e['accepted'] for e in architecture)
        assert max(result['population'][-1]['costs'])<20
    assert result['selected']['cost']<20
    assert (tmp_path/'case/selection-freeze.json').exists()

def test_untrained_copy_is_not_winner():
    assert joint.choose([dict(trained=False,cost=0,label='copy'),dict(trained=True,cost=1,label='trained')])['label']=='trained'
    with pytest.raises(ValueError):joint.choose([dict(trained=False,cost=0,label='copy')])

def test_frozen_global_work_arithmetic():
    allocation=read(BASE/'joint-allocation.json')
    assert allocation['work_limits']['sac_updates']==6*4928+3*5248
    assert allocation['work_limits']['transitions']==9*20480
    assert allocation['per_method_per_seed']['gradient_components']==4*4928+3*256+2*256==4*5248
