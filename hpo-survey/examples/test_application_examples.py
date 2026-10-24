import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from application_examples import (DESIGN, Objective, EvaluationContext, Policy,
    logistic_fit, logistic_score, neural_fit, neural_score, publish, digest, load_artifact)
from independent_checks import logistic_reference, network_reference, verify_payload, verify_regret


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_logistic_convex_kkt_and_scoring(self):
        obj=Objective('response',101,self.tmp.name)
        train=[v for k,v in obj.records.items() if k.startswith('train_')]
        score=[v for k,v in obj.records.items() if k.startswith('validation_')]
        for config in obj.configurations:
            physical=obj.physical(config);fit=logistic_fit(physical,train)
            loss,kkt=logistic_reference(fit['weights'],train,score,**physical)
            self.assertLessEqual(kkt,1.01e-9)
            self.assertAlmostEqual(loss,logistic_score(fit,score)[0],places=12)
        wrong=fit['weights'].copy();wrong[0]+=.1
        self.assertGreater(logistic_reference(wrong,train,score,**physical)[1],1e-4)

    def test_trained_architecture_and_derivative_oracle(self):
        obj=Objective('equilibrium',101,self.tmp.name)
        rows=[v for k,v in obj.records.items() if k.startswith('train_')]
        sizes=set()
        for width in (2,4,8):
            for depth in (1,2):
                config={'width':width,'depth':depth,'learning_rate':.03}
                fitted=neural_fit(config,rows,7);sizes.add(fitted['parameters'])
                loss,metrics=neural_score(fitted,rows[:8])
                y,jac=network_reference(fitted['layers'],rows[:8])
                np.testing.assert_allclose(y,metrics['y'],atol=1e-13)
                np.testing.assert_allclose(jac,metrics['jacobian'],atol=1e-13)
                torch.manual_seed(7);initial=Policy(width,depth)
                self.assertNotEqual(initial.net[0].weight.detach().tolist(),fitted['layers'][0]['weight'])
        self.assertEqual(len(sizes),6)

    def test_analytic_equilibrium_reference(self):
        cfg=DESIGN['equilibrium'];x=np.linspace(-.8,.8,17);a=np.linspace(.12,.48,17)
        slope=a/(1-cfg['beta']*cfg['rho']);y=slope*x
        np.testing.assert_allclose(y-cfg['beta']*slope*cfg['rho']*x-a*x,0,atol=1e-15)
        self.assertAlmostEqual(float(max(abs(slope*x-y))),0)

    def test_artifact_and_role_negative_controls(self):
        obj=Objective('response',101,self.tmp.name);fold=obj.declaration.tuning_folds[0]
        context=EvaluationContext('tuning',fold,obj.declaration.identity)
        result=obj({'alpha':0,'l1_ratio':0},0,context,'check')
        p=load_artifact(result['artifacts']['model']);verify_payload(p,obj.records,DESIGN)
        broken=copy.deepcopy(p);broken['model']['weights'][0]+=.1
        with self.assertRaises(AssertionError):verify_payload(broken,obj.records,DESIGN)
        broken=copy.deepcopy(p);broken['score_ids']=broken['train_ids']
        with self.assertRaises(AssertionError):verify_payload(broken,obj.records,DESIGN)
        path=Path(result['artifacts']['model']);doc=json.loads(path.read_text());doc['payload']['loss']+=1;path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):load_artifact(path)
        with self.assertRaises(ValueError):obj.physical({'alpha':99,'l1_ratio':0})
        with self.assertRaises(ValueError):obj({'alpha':0,'l1_ratio':0},0,EvaluationContext('tuning',fold,'wrong'),'bad')

    def test_data_roles_and_frozen_budgets(self):
        verify_regret(.125, .375, [.5, .25, .75])
        with self.assertRaises(AssertionError):
            verify_regret(0., .375, [.5, .25, .75])
        with self.assertRaises(AssertionError):
            verify_regret(-.1, .15, [.5, .25, .75])
        for name,n in [('response',15),('equilibrium',18)]:
            obj=Objective(name,202,self.tmp.name)
            self.assertEqual(len(obj.configurations),n)
            self.assertLess(DESIGN['search_budget'],n)
            self.assertGreater(DESIGN['search_budget'],10)
            t=obj.declaration.tuning_folds[0];f=obj.declaration.final_folds[0]
            self.assertFalse(set(t.train_ids+t.score_ids)&set(f.score_ids))
            self.assertEqual(set(f.train_ids),set(t.train_ids+t.score_ids))
            self.assertFalse(set(obj.declaration.tuning_seeds)&set(obj.declaration.final_seeds))

    def test_neural_tamper_and_work_reconstruction(self):
        obj=Objective('equilibrium',101,self.tmp.name)
        result=obj({'width':0,'depth':0,'learning_rate':0},0,
                   EvaluationContext('tuning',obj.declaration.tuning_folds[0],obj.declaration.identity),'nn')
        p=load_artifact(result['artifacts']['model']);verify_payload(p,obj.records,DESIGN)
        p['model']['layers'][0]['weight'][0][0]+=.1
        with self.assertRaises(AssertionError):verify_payload(p,obj.records,DESIGN)


if __name__=='__main__':unittest.main(verbosity=2)
