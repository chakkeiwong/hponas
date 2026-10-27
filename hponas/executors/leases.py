"""Cooperative per-user host leases; never claims to exclude unrelated apps."""
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess


def canonical_gpu_ids(ids):
    if not ids:return ()
    output=subprocess.run(['nvidia-smi','--query-gpu=index,uuid','--format=csv,noheader'],
        capture_output=True,text=True,check=True,timeout=10).stdout
    mapping={}
    for line in output.splitlines():
        index,uuid=(x.strip() for x in line.split(','))
        mapping[index]=uuid;mapping[uuid]=uuid
    try:canonical=tuple(mapping[str(x)] for x in ids)
    except KeyError as exc:raise ValueError('GPU identifier is not an available whole device') from exc
    if len(set(canonical))!=len(canonical):raise ValueError('GPU aliases resolve to the same physical device')
    return canonical


class HostLeases:
    def __init__(self, placements):
        self.handles=[]
        root=Path('/tmp')/('hponas-resource-leases-'+str(os.getuid()))
        if root.is_symlink():raise ValueError('Resource lease directory must not be a symlink')
        root.mkdir(mode=0o700,exist_ok=True)
        if root.stat().st_uid!=os.getuid():raise ValueError('Resource lease directory has another owner')
        names={f'cpu-{c}' for p in placements for c in p.cpu_ids}
        names|={'gpu-'+hashlib.sha256(g.encode()).hexdigest() for p in placements for g in p.gpu_ids}
        try:
            for name in sorted(names):
                fd=os.open(root/name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
                handle=os.fdopen(fd,'a')
                self.handles.append(handle)
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise ValueError('Requested CPU/GPU lease is already held or unavailable')

    def close(self):
        for handle in self.handles:handle.close()
        self.handles=[]
