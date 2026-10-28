from hponas_rl_lqr5.catalog import sac_config as predecessor_config
from .environment import FiniteLQR10Env

def sac_config(config,seed=0):
    return predecessor_config(config,seed).environment(env=FiniteLQR10Env)
