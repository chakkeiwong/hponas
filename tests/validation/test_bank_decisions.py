"""Independent financial arithmetic, observable likelihood and bounded decisions."""
from fractions import Fraction as F
import math

import pytest

from workloads.bank_decisions import (decision_profile,discounted_value,exact_allocation,
    portfolio_utility,robust_allocation,reload_decision,survival_counts)
from validation.bank_references import valuation_reference,allocation_reference

TOL=2.**-38


@pytest.mark.parametrize('name',['valuation','valuation_unidentified','wallet','allocation','allocation_uncertain'])
def test_every_statistical_choice_has_independent_formula_and_honest_decision(name):
    profile=decision_profile(name);key,choices=next(iter(profile.choices.items()))
    for fold in profile.declaration.tuning_folds+profile.declaration.final_folds:
        for choice in choices:
            actual=profile.evaluate({key:choice},fold);a=actual['assessment']
            if name.startswith('valuation'):
                reference=valuation_reference(choice)
                assert actual['loss']==pytest.approx(reference['loss'],abs=TOL)
                if name=='valuation':
                    assert a['npv']==pytest.approx(reference['npv'],abs=TOL)
                    assert reload_decision(actual['model'])['npv']==a['npv']
                else:
                    assert a['npv'] is None and reload_decision(actual['model'])['npv'] is None
                    assert a['bounds']==pytest.approx([-100.,float(F(500,121))],abs=TOL)
            elif name=='wallet':
                assert actual['loss']==pytest.approx(math.log(2),abs=TOL)
                assert a['latent_mean'] is None and a['bounds']==[1.5,2.]
                assert reload_decision(actual['model'])['bounds']==a['bounds']
            else:
                expected=allocation_reference(choice,uncertain=name=='allocation_uncertain')
                assert actual['loss']==pytest.approx(expected['loss'],abs=TOL)
                assert a['weight']==pytest.approx(expected['weight'],abs=TOL)
                assert a['decision_regret']==pytest.approx(expected['regret'],abs=TOL)
                assert reload_decision(actual['model'])['weight']==a['weight']
                if name=='allocation_uncertain':
                    assert a['point_identified_optimum'] is None
                    assert a['possible_optimal_weights']==pytest.approx([.24,.56],abs=TOL)
                    assert a['candidate_worst_case_utility']==pytest.approx(-actual['loss'],abs=TOL)
                    assert a['worst_case_utility']>=a['candidate_worst_case_utility']-TOL


def test_censored_wallet_tail_mixtures_are_observationally_identical_but_means_differ():
    distributions=[(F(1,2),F(1,2),F(0)),(F(1,2),F(0),F(1,2))]
    likelihoods=[p1**2*(p2+p3)**2 for p1,p2,p3 in distributions]
    means=[sum(F(i)*p for i,p in enumerate(row,1)) for row in distributions]
    assert likelihoods==[F(1,16),F(1,16)]
    assert means==[F(3,2),F(2)]
    assert distributions[1][1]==0  # Treating a censored 2 as exact would give zero likelihood.


def test_signed_discount_and_censoring_terms_cannot_be_dropped():
    value=discounted_value([(0,-100.),(1,60.),(2,60.)],.1)
    assert value==pytest.approx(float(F(500,121)),abs=TOL)
    assert discounted_value([(0,100.),(1,60.),(2,60.)],.1)==pytest.approx(value+200)
    assert discounted_value([(0,-100.),(1,60.),(2,60.)],.1,0.)==-100.
    rows=[{'time':t,'event':e,'identified':True} for t,e in [(1,1),(2,1),(2,0),(2,0)]]
    assert survival_counts(rows)==(2,5)
    with pytest.raises(ValueError):survival_counts([{'time':1.5,'event':1,'identified':True}])
    with pytest.raises(ValueError):discounted_value([(0,-100.),(0,60.)],.1)
    with pytest.raises(ValueError):discounted_value([(0,-100.)],-1.)


def test_qp_solution_agrees_with_independent_dense_grid_and_lp_limits():
    for means in [(0.1,.05),(-1.,1.),(1.,-1.),(.05,.05)]:
        actual=exact_allocation(means);w=actual['weight']
        grid=[i/1000 for i in range(1001)]
        values=[portfolio_utility(x,means) for x in grid]
        assert actual['utility']>=max(values)-TOL
        if 0<w<1:
            # Derivative of the independently expanded quadratic is zero.
            assert means[0]-means[1]-.25*w+.05==pytest.approx(0,abs=TOL)
    assert exact_allocation((.1,.05),risk_aversion=0)['weight']==1
    assert exact_allocation((.05,.1),risk_aversion=0)['weight']==0
    tie=exact_allocation((.1,.1),risk_aversion=0)
    assert tie['weight'] is None and tie['optimal_weights']==[0,1]
    with pytest.raises(ValueError,match='Positive definite'):exact_allocation((.1,.05),((1.,2.),(2.,1.)))
    with pytest.raises(ValueError):exact_allocation((.1,.05),risk_aversion=-1)


def test_interval_mean_allocation_retains_robust_choice_and_possible_optimum_range():
    result=robust_allocation([[.08,.12],[.03,.07]])
    assert result['robust_weight']==pytest.approx(.4,abs=TOL)
    corner_weights=[exact_allocation((a,b))['weight'] for a in (.08,.12) for b in (.03,.07)]
    assert result['possible_optimal_weights']==pytest.approx([min(corner_weights),max(corner_weights)],abs=TOL)
    with pytest.raises(ValueError,match='reversed'):robust_allocation([[.12,.08],[.03,.07]])
