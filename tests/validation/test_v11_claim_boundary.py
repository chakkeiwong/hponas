"""Pilot significance and heuristic portfolio sampling cannot certify V11."""

from types import SimpleNamespace

import pytest

from hponas import Knob, SearchSpace
from validation import v11_campaign as campaign


def favorable_result(mode, manifest_digest=None):
    return campaign.CampaignResult(
        mode=mode, n_replicates=5, n_trials=25, study_results=[],
        tests={"V11a": SimpleNamespace(clears=lambda alpha: True)},
        clusters={}, missingness={},
        holm=[SimpleNamespace(entry_id="V11a", reject=True, adjusted_alpha=.01)],
        prior_support=[], manifest_digest=manifest_digest,
    )


@pytest.mark.parametrize("mode,digest", [("pilot", None), ("pilot", "pretend"), ("confirmatory", None)])
def test_favorable_numbers_without_confirmatory_provenance_are_inconclusive(mode, digest):
    assert favorable_result(mode, digest).verdict("V11a") == "inconclusive"


def test_excessive_missingness_still_voids_pilot():
    result = favorable_result("pilot")
    result.voided = True
    assert result.verdict("V11a") == "void"


def test_certified_register_cannot_override_missing_method_conformance(monkeypatch):
    monkeypatch.setattr(campaign, "_register_permits_confirmatory", lambda: (True, "test"))
    with pytest.raises(RuntimeError, match="faithful PriorBand"):
        campaign.run_campaign(mode="confirmatory")


def test_partial_method_list_cannot_claim_both_registered_methods():
    with pytest.raises(ValueError, match="both piBO and PriorBand"):
        campaign.run_campaign(mode="confirmatory", methods=["pibo"])


@pytest.mark.parametrize("count,rungs", [(1, 3), (2, 3), (4, 3), (25, 3), (8, 2)])
def test_heuristic_diagnostic_spends_exact_requested_trial_count(count, rungs):
    seen = []

    def objective(config):
        seen.append(config)
        return config["x"]**2

    task = SimpleNamespace(task_id="count-probe", direction="minimize",
                           space=lambda: SearchSpace([Knob("x", "continuous", (0., 1.))]),
                           objective=objective)
    result = campaign.run_priorband_study(task, "no_prior", 42, n_trials=count, n_rungs=rungs)
    assert result.error is None
    assert result.n_trials == len(seen) == count
    assert result.best_value == min(config["x"]**2 for config in seen)


@pytest.mark.parametrize("argument,value", [("n_trials", 0), ("n_trials", True), ("n_rungs", 0)])
def test_invalid_diagnostic_budget_is_rejected_before_work(argument, value):
    with pytest.raises(ValueError, match="positive integer"):
        campaign.run_priorband_study(None, "no_prior", 42, **{argument: value})
