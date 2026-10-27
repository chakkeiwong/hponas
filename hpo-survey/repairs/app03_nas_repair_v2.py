import itertools,sys
from common import *
from nas_repair_model_v2 import train,evaluate,mesh,LIMITS
def run(out):
    rows=[]
    for seed,width,geometry,recipe in itertools.product((6401,6402),(4,8),('random','tensor'),('raw','normalized','polish')):
        row=train(seed,width,geometry,recipe);row.update(seed=seed,width=width,geometry=geometry,recipe=recipe,validation=evaluate(row['model'],mesh(41)))
        save(out/f'{seed}-{width}-{geometry}-{recipe}.json',row);rows.append(row)
        print(canon({k:row[k] for k in ('seed','width','geometry','recipe','seconds')}),flush=True)
    assert len(rows)==24;groups=[]
    for width,geometry,recipe in itertools.product((4,8),('random','tensor'),('raw','normalized','polish')):
        chosen=[r for r in rows if (r['width'],r['geometry'],r['recipe'])==(width,geometry,recipe)]
        groups.append({'width':width,'geometry':geometry,'recipe':recipe,'all_validation_feasible':all(r['validation']['feasible'] for r in chosen),'worst_validation_ratio':max(r['validation']['max_limit_ratio'] for r in chosen),'mean_validation_loss':sum(r['validation']['loss'] for r in chosen)/2,'parameters':chosen[0]['model']['parameters']})
    feasible=[g for g in groups if g['all_validation_feasible']]
    selected=min(feasible,key=lambda g:(g['parameters'],g['worst_validation_ratio'],g['mean_validation_loss'])) if feasible else min(groups,key=lambda g:g['worst_validation_ratio'])
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'validation_recipe_found' if feasible else 'validation_nonattainment','fits':24,'limits':LIMITS,'groups':groups,'selected':selected,'selection_rule':'Require both development seeds feasible; minimize parameters then worst validation ratio then mean loss. If none, retain closest as explicit failed-development confirmation.','fresh_confirmation_seeds':[7401,7402,7403,7404,7405,7406],'final_data_seen':False})
if __name__=='__main__':run(Path(sys.argv[1]))
