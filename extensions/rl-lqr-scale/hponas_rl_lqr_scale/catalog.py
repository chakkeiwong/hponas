"""Known dynamics/reward, learned full PSD continuation; optional sign symmetry."""
import torch
from ray.rllib.core.rl_module.rl_module import RLModuleSpec
from hponas_rl_lqr5.catalog import LiteralSACCatalog,sac_config as original
from .reference import LQRSpec
from .environment import ScaleLQREnv

class MatrixEncoder(torch.nn.Module):
    def __init__(self,hiddens,spec):
        super().__init__();self.states=spec.states;self.actions=spec.actions;self.gamma=spec.gamma;self.horizon=spec.horizon
        for name,array in [('A',spec.A),('B',spec.B),('Q',spec.Q),('R',spec.R),('w',spec.noise_vector)]:self.register_buffer(name,torch.tensor(array,dtype=torch.float32))
        tri=torch.tril_indices(spec.states,spec.states);self.register_buffer('rows',tri[0]);self.register_buffer('cols',tri[1]);self.register_buffer('diag',tri[0]==tri[1])
        layers=[];sizes=[1,*hiddens]
        for a,b in zip(sizes,sizes[1:]):layers.extend([torch.nn.Linear(a,b),torch.nn.Tanh()])
        layers.append(torch.nn.Linear(sizes[-1],len(self.rows)+1));self.network=torch.nn.Sequential(*layers)
        torch.nn.init.zeros_(layers[-1].weight);torch.nn.init.zeros_(layers[-1].bias)
    def continuation(self,time):
        raw=self.network(time);coeff=torch.where(self.diag,torch.nn.functional.softplus(raw[:,:-1]),raw[:,:-1])
        L=torch.zeros((len(time),self.states,self.states),dtype=time.dtype,device=time.device);L[:,self.rows,self.cols]=coeff
        matrix=L@L.transpose(-1,-2);terminal=time[:,0]<1.5/self.horizon
        matrix=torch.where(terminal[:,None,None],self.Q[None],matrix);c=torch.where(terminal,torch.zeros_like(raw[:,-1]),raw[:,-1])
        return matrix,c
    def forward(self,batch):
        obs,u=batch['obs'],batch['actions'];x=obs[:,:self.states];p,c=self.continuation(obs[:,-1:]);y=x@self.A.T+u@self.B.T
        stage=(x*(x@self.Q)).sum(-1)+(u*(u@self.R)).sum(-1)
        future=torch.einsum('bi,bij,bj->b',y,p,y)+torch.einsum('i,bij,j->b',self.w,p,self.w)
        return {'encoder_out':(-stage+self.gamma*(c-future))[:,None]}

class PairEncoder(torch.nn.Module):
    def __init__(self,base,symmetric):super().__init__();self.base=base;self.symmetric=symmetric
    def forward(self,batch):
        one=self.base(batch)['encoder_out']
        if not self.symmetric:return {'encoder_out':one}
        obs=batch['obs'];reflected=torch.cat((-obs[:,:-1],obs[:,-1:]),-1)
        two=self.base({'obs':reflected})['encoder_out']
        return {'encoder_out':torch.cat((one,two),-1)}

class PairHead(torch.nn.Module):
    def __init__(self,base,symmetric):super().__init__();self.base=base;self.symmetric=symmetric
    def forward(self,z):
        if not self.symmetric:return self.base(z)
        a,b=z.chunk(2,-1);mu1,sd1=self.base(a).chunk(2,-1);mu2,sd2=self.base(b).chunk(2,-1)
        return torch.cat(((mu1-mu2)/2,(sd1+sd2)/2),-1)

class ScaleCatalog(LiteralSACCatalog):
    def __init__(self,observation_space,action_space,model_config_dict,view_requirements=None):
        self.spec=LQRSpec.from_case(model_config_dict['scale_case']);self.symmetric=model_config_dict['scale_method']=='symmetric'
        super().__init__(observation_space,action_space,model_config_dict,view_requirements)
    def build_encoder(self,framework):return PairEncoder(super().build_encoder(framework),self.symmetric)
    def build_pi_head(self,framework):return PairHead(super().build_pi_head(framework),self.symmetric)
    def _build_qf_encoder_continuous(self,framework):return MatrixEncoder(self.critic_hiddens,self.spec)
    def build_qf_head(self,framework):return torch.nn.Identity()

def sac_config(config,seed=0,case='s1a5',method='matrix'):
    cfg=original(config,seed).environment(env=ScaleLQREnv,env_config={'case':case})
    return cfg.rl_module(model_config=dict(cfg.model_config,scale_case=case,scale_method=method),rl_module_spec=RLModuleSpec(catalog_class=ScaleCatalog))
