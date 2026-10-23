"""Static method declarations and independent admission counterexamples."""
from dataclasses import replace
import pytest

from hponas import (SearcherCapabilities, SearchSpace, Knob, LocalExecutor, Study,
                    RandomSearcher, SobolSearcher, GPSearcher, RobustGPSearcher,
                    CMAESSearcher, MultiObjectiveRandomSearcher, MultiObjectiveBayesSearcher,
                    WrappedNSGAIISearcher)
from hponas.capabilities import admit
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers.base import BaseSearcher
from hponas.searchers_tpe import TPESearcher
from hponas.searchers_gp import GPqLogEISearcher
from hponas.searchers.adapter import LegacySearcherAdapter


def continuous(n=1):
    return SearchSpace([Knob('x'+str(i), 'continuous', (0., 1.)) for i in range(n)])


def conditional():
    return SearchSpace([Knob('model', 'categorical', ['a', 'b']),
                        Knob('width', 'ordinal', (1, 3), condition=('model', 'b'))])


@pytest.mark.parametrize('factory', [RandomSearcher, SobolSearcher, GPSearcher])
def test_support_does_not_change_with_supplied_parameter_kinds(factory):
    a, b = factory(continuous()), factory(conditional())
    assert a.support == b.support
    assert a.capabilities['parameter_types'] == ['continuous', 'ordinal', 'categorical']
    assert a.capabilities['conditionals'] is True


def test_base_does_not_infer_capabilities_from_input():
    class Unspecified(BaseSearcher):
        def suggest(self): return RandomSearcher(self.search_space).suggest()
    searcher = Unspecified(conditional())
    assert searcher.capabilities['parameter_types'] == []
    with pytest.raises(ValueError, match='explicit searcher capabilities'):
        admit(searcher, scheduler=None, workers=1, declared=True)
    assert admit(searcher, scheduler=None, workers=1, declared=False)['status'] == 'legacy_unverified_capabilities'


@pytest.mark.parametrize('field,value,space_factory,kwargs,message', [
    ('kinds', ('continuous',), conditional, {}, 'parameter kinds'),
    ('conditionals', False, conditional, {}, 'conditional'),
    ('partial_fidelity', False, continuous, {'scheduler':dict(r_min=1,r_max=2)}, 'partial-fidelity'),
    ('concurrent_proposals', False, continuous, {'workers':2}, 'sequential'),
    ('architecture_coordinates', False, continuous, {'architecture':('x0',)}, 'architecture'),
    ('max_dimensions', 1, lambda: continuous(2), {}, 'dimension'),
    ('failed_observations', False, continuous, {}, 'failed-observation'),
    ('objectives', 'vector', continuous, {}, 'objective capability'),
])
def test_uniform_refusal_uses_explicit_contract(field, value, space_factory, kwargs, message):
    searcher = RandomSearcher(space_factory())
    searcher.support = replace(searcher.support, **{field:value})
    options = dict(scheduler=None, workers=1, declared=True)
    options.update(kwargs)
    if options["scheduler"] is not None:
        options["scheduler"] = ASHAScheduler(ASHAConfig(**options["scheduler"]))
    with pytest.raises(ValueError, match=message): admit(searcher, **options)
    assert not searcher.history and not searcher.trials


def test_declared_prior_metadata_is_not_silently_ignored():
    space = SearchSpace([Knob('x', 'continuous', (0., 1.), prior={'mean':.5})])
    with pytest.raises(ValueError, match='explicit supported prior law'):
        Study(RandomSearcher(space), LocalExecutor(), lambda c: 0., legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')


def test_scalar_gp_partial_results_refused_before_trial_creation():
    searcher = GPSearcher(continuous())
    with pytest.raises(ValueError, match='partial-fidelity'):
        Study(searcher, LocalExecutor(), lambda c: 0., scheduler=ASHAScheduler(ASHAConfig(r_min=1,r_max=2)), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    assert not searcher.trials


def test_actual_method_restrictions_and_wrappers_remain_visible():
    assert CMAESSearcher(continuous()).support.kinds == ('continuous',)
    robust = RobustGPSearcher(continuous())
    assert robust.support.max_dimensions == 16
    assert robust.support.concurrent_proposals is False
    assert robust.support.failed_observations is False
    for method, kinds, conditional, prior in [
        (TPESearcher(continuous()), ('continuous','ordinal','categorical'), True, 'none'),
        (GPqLogEISearcher(continuous()), ('continuous',), False, 'density_function'),
    ]:
        wrapper = LegacySearcherAdapter(method)
        assert wrapper.support.kinds == kinds and wrapper.support.conditionals == conditional
        assert wrapper.support.prior == prior
        assert wrapper.capabilities['support_contract'] == wrapper.support.contract


def test_vector_support_and_constraint_counterexample():
    objectives = [{'name':'a','direction':'min','lower':0.,'upper':1.},
                  {'name':'b','direction':'min','lower':0.,'upper':1.}]
    for cls, kinds, conditional in [
        (MultiObjectiveRandomSearcher, ('continuous','ordinal','categorical'), True),
        (MultiObjectiveBayesSearcher, ('continuous','ordinal'), False),
        (WrappedNSGAIISearcher, ('continuous','ordinal','categorical'), False),
    ]:
        searcher = cls(continuous(), objectives=objectives, constraints={'residual':.1})
        assert searcher.support.kinds == kinds and searcher.support.conditionals == conditional
        assert searcher.support.partial_fidelity is True
        searcher.support = replace(searcher.support, constraints=False)
        with pytest.raises(ValueError, match='constraint measurements'):
            admit(searcher, scheduler=None, workers=1, declared=True)


def test_architecture_coordinates_require_names_and_survive_resume(tmp_path):
    a = Study(RandomSearcher(continuous(),seed=1), LocalExecutor(), lambda c: c['x0'],
              budget=1, architecture_coordinates=('x0',), checkpoint_dir=tmp_path, study_name='architecture', legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    a.run()
    b = Study(RandomSearcher(continuous(),seed=1), LocalExecutor(), lambda c: c['x0'], legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    with pytest.raises(ValueError, match='architecture declaration'):
        b.load_checkpoint(tmp_path/'architecture_checkpoint.json')
    with pytest.raises(ValueError, match='distinct search-space knobs'):
        Study(RandomSearcher(continuous()), LocalExecutor(), lambda c: 0., architecture_coordinates=('missing',), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
