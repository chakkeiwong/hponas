"""Shared-device admission based on memory; utilization is a preference only."""
import subprocess


def shared_admission(query, processes):
    devices=[]
    for line in query.splitlines():
        if not line.strip(): continue
        uuid,utilization,free,total=[x.strip() for x in line.split(',')]
        devices.append({'uuid':uuid,'utilization_percent':int(utilization),
                        'free_mib':int(free),'total_mib':int(total)})
    eligible=sorted((d for d in devices if d['free_mib']>=4096),
                    key=lambda d:(d['utilization_percent'],-d['free_mib'],d['uuid']))
    return {'devices':devices,'gpu_query':query,'compute_processes':processes,
            'selected_gpu_ids':[d['uuid'] for d in eligible[:2]],'passed':len(eligible)>=2,
            'required':2,'idle_required':False,'minimum_free_mib':4096,
            'torch_allocator_limit_bytes':1024**3,'owned_process_limit_mib':2048}


def admit():
    query=subprocess.check_output(['/usr/bin/nvidia-smi',
        '--query-gpu=uuid,utilization.gpu,memory.free,memory.total','--format=csv,noheader,nounits'],text=True)
    processes=subprocess.check_output(['/usr/bin/nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory',
                                       '--format=csv,noheader,nounits'],text=True)
    return shared_admission(query,processes)
