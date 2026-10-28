from hponas_rl_lqr5.catalog import sac_config as predecessor_config
from .environment import ScalarLQREnv

def sac_config(config,seed=0,case='scalar3'):
    return predecessor_config(config,seed).environment(env=ScalarLQREnv,env_config={'case':case})
