import sys
import numpy as np
from common import *
from nas_repair_model_v2 import train,evaluate,mesh,LIMITS
def run(out):
    manifest=read(BASE/'nas-confirm-manifest.json');development=read(ROOT/manifest['development_result']);cfg=development['selected'];rows=[]
    for seed in (7401,7402,7403,7404,7405,7406):
        row=train(seed,cfg['width'],cfg['geometry'],cfg['recipe']);final=np.random.default_rng(seed+100000).uniform([-.5,.2],[.5,.6],(512,2))
        row.update(seed=seed,final_points=final.tolist(),final_mesh=evaluate(row['model'],mesh(81)),final_random=evaluate(row['model'],final));save(out/f'confirmation-{seed}.json',row);rows.append(row)
        print(canon({'seed':seed,'ratio':row['final_mesh']['max_limit_ratio']}),flush=True)
    passed=all(r['final_mesh']['feasible'] and r['final_random']['feasible'] for r in rows)
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'finite_confirmation_pass' if passed else 'finite_confirmation_fail','fits':6,'selected':cfg,'limits':LIMITS,'mesh_feasible':sum(r['final_mesh']['feasible'] for r in rows),'random_feasible':sum(r['final_random']['feasible'] for r in rows),'worst_mesh_ratio':max(r['final_mesh']['max_limit_ratio'] for r in rows),'continuous_domain_certified':False,'all_seed_guarantee':False})
if __name__=='__main__':run(Path(sys.argv[1]))
