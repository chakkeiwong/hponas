"""Fixture-specific critic controls, with unchanged upstream SAC losses.

Quadratic assumes an even concave value. Informed uses known one-step dynamics,
reward and terminal cost, but no Riccati solution. Neither is generic model-free
qualification. Plain delegates to the original catalog exactly.
"""
import math
import torch
from ray.rllib.core.rl_module.rl_module import RLModuleSpec
from hponas_rl_lqr5.catalog import LiteralSACCatalog
from hponas_rl_lqr_scalar.catalog import sac_config as original

class StructuredEncoder(torch.nn.Module):
    def __init__(self, hiddens, actions, method):
        super().__init__()
        self.actions, self.method = actions, method
        n=1+actions
        self.register_buffer('tri_rows',torch.tril_indices(n,n)[0])
        self.register_buffer('tri_cols',torch.tril_indices(n,n)[1])
        self.register_buffer('diagonal_mask',self.tri_rows==self.tri_cols)
        widths=[1,*hiddens];layers=[]
        for a,b in zip(widths,widths[1:]):layers.extend([torch.nn.Linear(a,b),torch.nn.Tanh()])
        outputs=2 if method=='informed' else n*(n+1)//2+1
        layers.append(torch.nn.Linear(widths[-1],outputs));self.network=torch.nn.Sequential(*layers)
        # A fixed parameterization prior, not fitted oracle coefficients.
        torch.nn.init.zeros_(layers[-1].weight);torch.nn.init.zeros_(layers[-1].bias)
    def forward(self,batch):
        obs,u=batch['obs'],batch['actions'];x=obs[:,0];remaining=obs[:,-1:]
        raw=self.network(remaining)
        if self.method=='informed':
            p=torch.nn.functional.softplus(raw[:,0]);c=raw[:,1]
            terminal=remaining[:,0]<1.5/30
            p=torch.where(terminal,torch.ones_like(p),p)
            c=torch.where(terminal,torch.zeros_like(c),c)
            y=.92*x+u.sum(-1)/math.sqrt(self.actions)
            q=-x.square()-.1*u.square().sum(-1)+.99*(c-p*(y.square()+.025**2))
        else:
            n=1+self.actions
            coeff=torch.where(self.diagonal_mask,torch.nn.functional.softplus(raw[:,:-1]),raw[:,:-1])
            lower=torch.zeros((len(obs),n,n),dtype=obs.dtype,device=obs.device)
            lower[:,self.tri_rows,self.tri_cols]=coeff
            z=torch.cat((x[:,None],u),-1)
            q=raw[:,-1]-torch.bmm(z[:,None,:],lower).squeeze(1).square().sum(-1)
        return {'encoder_out':q[:,None]}

class StructuredCatalog(LiteralSACCatalog):
    def __init__(self,observation_space,action_space,model_config_dict,view_requirements=None):
        self.method=model_config_dict['repair_method']
        super().__init__(observation_space,action_space,model_config_dict,view_requirements)
    def _build_qf_encoder_continuous(self,framework):
        if framework!='torch':raise ValueError('Torch required')
        return StructuredEncoder(self.critic_hiddens,self.action_space.shape[0],self.method)
    def build_qf_head(self,framework):return torch.nn.Identity()

def sac_config(config,seed=0,case='scalar3',method='plain'):
    cfg=original(config,seed,case)
    if method!='plain':
        if case!='scalar3':raise ValueError('Reviewed structured control is scalar3 only')
        cfg.rl_module(model_config=dict(cfg.model_config,repair_method=method),
                      rl_module_spec=RLModuleSpec(catalog_class=StructuredCatalog))
    return cfg
