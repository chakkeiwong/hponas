import numpy as np
import torch

def action_rows(actor,states,time):
    obs=np.column_stack((states,np.full(len(states),(30-time)/30))).astype(np.float32)
    unique,inverse=np.unique(obs,axis=0,return_inverse=True)
    with torch.no_grad():values=actor(torch.from_numpy(unique)).cpu().numpy()
    return values[inverse]
