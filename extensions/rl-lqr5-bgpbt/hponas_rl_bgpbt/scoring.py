"""Nonanticipating finite-law inference, with canonical unique observations.

Float32 GEMM kernels can give slightly different values for duplicate rows at
different positions (e.g. vectorized body versus tail). Repeated history nodes
must share one action. Otherwise an evaluator can accidentally correlate tiny
rounding errors with future noise through path index. Canonicalization enforces
the policy's information set without relaxing the Riccati identity tolerance.
"""
import numpy as np
import torch


def action_rows(actor, states, time):
    observations=np.column_stack((states,np.full(len(states),(8-time)/8))).astype(np.float32)
    unique,inverse=np.unique(observations,axis=0,return_inverse=True)
    with torch.no_grad(): actions=actor(torch.from_numpy(unique)).cpu().numpy()
    return actions[inverse]
