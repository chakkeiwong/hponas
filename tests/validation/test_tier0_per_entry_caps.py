"""Bounded artifact fixtures for entry caps; no real workload or allocation."""

import copy
import json
from pathlib import Path

import pytest

from validation.tier0_design import canonical_digest, resource_limits
from validation.tier0_objectivity import require_resource_authorization
from validation.tier0_pilot_sizing import verify_sizing_receipt
from validation.tier0_rank_campaign import freeze_search_bundle, recompute_protected
from tests.validation.test_tier0_objectivity import bind as authorization_binding
from tests.validation.test_tier0_pilot_sizing import sizing_bridge
from tests.validation.test_tier0_rank_campaign import (
    fixture_campaign, evaluate_fixture, read, write,
)


def separate_caps(design, total=10000, protected=1000):
    design["resource"].pop("campaign_cap_seconds", None)
    design["resource"].pop("protected_cap_seconds", None)
    design["resource"]["entry_caps"] = {
        entry: {"campaign_cap_seconds": total, "protected_cap_seconds": protected}
        for entry in ("V04-T0", "V05")}


def freeze_entry(fixture, entry="V05"):
    design, root, refs = fixture
    updated = []
    for ref in refs:
        record = read(ref)
        if record["entry"] == entry:
            record["design_digest"] = canonical_digest(design)
            updated.append(write(Path(ref["path"]), record))
    return freeze_search_bundle(design, root, updated, entries=[entry], phase="pilot")


@pytest.mark.parametrize("fault", ["mixed", "missing-entry", "extra-entry", "boolean", "infinite", "partial", "over-total", "legacy-schema"])
def test_ambiguous_or_invalid_reservations_are_refused(fault):
    d = {"schema_version": 2, "resource": {}}
    separate_caps(d)
    if fault == "mixed": d["resource"]["campaign_cap_seconds"] = 100000
    if fault == "missing-entry": del d["resource"]["entry_caps"]["V05"]
    if fault == "extra-entry": d["resource"]["entry_caps"]["V99"] = {}
    if fault == "boolean": d["resource"]["entry_caps"]["V05"]["campaign_cap_seconds"] = True
    if fault == "infinite": d["resource"]["entry_caps"]["V05"]["campaign_cap_seconds"] = float("inf")
    if fault == "partial": del d["resource"]["entry_caps"]["V05"]["protected_cap_seconds"]
    if fault == "over-total": d["resource"]["entry_caps"]["V05"]["protected_cap_seconds"] = 20000
    if fault == "legacy-schema": d["schema_version"] = 1
    with pytest.raises(ValueError):
        resource_limits(d, "V04-T0")  # Bad other-entry caps cannot remain hidden.


def test_small_entry_cannot_spend_the_large_entry_protected_allocation(fixture_campaign):
    design, root, _ = fixture_campaign
    separate_caps(design)
    design["resource"]["entry_caps"]["V05"]["protected_cap_seconds"] = 2
    frozen = freeze_entry(fixture_campaign)
    evaluated, calls = evaluate_fixture(root, frozen)
    assert len(calls) == 2
    assert read(evaluated)["effective_cap_seconds"] == 2
    report = recompute_protected(root, frozen, evaluated)
    assert report["entries"]["V05"]["counts"]["loss_cap_void"]
    forged = read(evaluated)
    forged["effective_cap_seconds"] = 1000
    rebound = write(Path(evaluated["path"]), forged)
    with pytest.raises(ValueError, match="cap exceeds frozen allocation"):
        recompute_protected(root, frozen, rebound)


def test_entry_limits_cannot_be_pooled():
    d = {"schema_version": 2, "resource": {}}
    separate_caps(d)
    with pytest.raises(ValueError, match="pooling"):
        resource_limits(d)
    with pytest.raises(ValueError, match="pooling"):
        resource_limits(d, "V16")


def test_permission_must_bind_exact_entry_amounts_and_cannot_be_swapped(tmp_path):
    d = {"schema_version": 2, "sampling": {"selection_algorithm": "prospective_named_suite_local_v1"},
         "resource": {}, "run_schedule": {"pilot": {"V04-T0": "a", "V05": "b"}}}
    separate_caps(d)
    d["resource"]["entry_caps"]["V05"]["campaign_cap_seconds"] = 2000
    receipt = {"kind": "tier0_resource_authorization", "scope": "resource_execution_only", "phase": "pilot",
        "design_digest": canonical_digest(d), "resource_digest": canonical_digest(d["resource"]),
        "authorization": "inert fixture, no real resource allocation", "run_schedule": d["run_schedule"],
        "entry_caps_seconds": {"V04-T0": 10000, "V05": 2000}}
    ref = authorization_binding(tmp_path, "correct.json", receipt)
    p = {"evidence": [{**ref, "kind": "tier0_resource_authorization", "phases": ["pilot"]}]}
    require_resource_authorization(d, "pilot", p, tmp_path)
    receipt["entry_caps_seconds"] = {"V04-T0": 2000, "V05": 10000}
    p["evidence"][0].update(authorization_binding(tmp_path, "swapped.json", receipt))
    with pytest.raises(ValueError, match="No hash-bound resource authorization"):
        require_resource_authorization(d, "pilot", p, tmp_path)


def test_confirmation_must_preserve_each_entries_per_vector_envelope(sizing_bridge):
    d, pilot, _, _, _, _, root = sizing_bridge
    separate_caps(pilot, total=100000, protected=50000)
    separate_caps(d, total=1600, protected=800)
    assert verify_sizing_receipt(d, "confirmation", root)["verdict"] == "SIZED"
    d["resource"]["entry_caps"]["V04-T0"]["protected_cap_seconds"] = 1500
    d["resource"]["entry_caps"]["V05"]["protected_cap_seconds"] = 1
    with pytest.raises(ValueError, match="shrinks the pilot allowance"):
        verify_sizing_receipt(d, "confirmation", root)


def test_v05_interior_missingness_is_still_a_veto_even_with_identical_final_scores(fixture_campaign):
    design, root, _ = fixture_campaign
    frozen = freeze_entry(fixture_campaign)
    evaluated, _ = evaluate_fixture(root, frozen)
    before = recompute_protected(root, frozen, evaluated)
    raw = read(evaluated)
    removed = raw["receipts"].pop(0)  # An early policy, not the final incumbent.
    assert read(removed["receipt"])["observation_index"] == 0
    updated = write(Path(evaluated["path"]), raw)
    after = recompute_protected(root, frozen, updated)
    assert before["entries"]["V05"]["lower_rows"] == after["entries"]["V05"]["lower_rows"]
    assert not before["entries"]["V05"]["counts"]["loss_cap_void"]
    assert after["entries"]["V05"]["counts"]["loss_cap_void"]
