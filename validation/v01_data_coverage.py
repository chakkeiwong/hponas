"""Reconstruct the authorized V01 supplement from every original source cell."""

from __future__ import annotations

import csv
import io

from validation.benchmark_catalog import LandscapeTable
from validation.tier0_objectivity import read_bound_json
from validation.v01_contract import RULE, _file

PRIOR = {"path": "validation/designs/v01_finite_corpus_v1.json",
         "sha256": "40ee305293d275b164fd0a12e3093783fee6fbb66418dcfada2b4092afe91994"}
MISSING = {"path": "docs/program/evidence/2026-09-30/v01-adoption/missing-cells-final.json",
           "sha256": "53926439bd83cde6d97a71adc552738bf51b077862db2ca773b4dda7d14f2312"}


def complete_domain_bytes(source, seed):
    """Include all finite full-fidelity configurations; preserve literal rows.

    Eligibility uses missingness only. No score magnitude, outcome ranking,
    optimizer history, alternate seed or truncated fidelity is considered.
    """
    table = LandscapeTable(source)
    if type(seed) is not int or seed not in table.seeds:
        raise ValueError("Complete-domain seed is absent")
    ids = sorted(c for c in table.configurations if all(
        table.cells.get((c, seed, step), {}).get("status") == "finite"
        for step in table.training_steps))
    if not ids:
        raise ValueError("No complete configurations at every original fidelity")
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    selected = [row for row in rows if int(row["seed"]) == seed and int(row["config_id"]) in ids]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(selected)
    return ids, sorted(table.training_steps), stream.getvalue().encode("utf-8")


def verify_complete_domain(row, root):
    derivation = row.get("derivation", {})
    if (row.get("role") != "complete_domain" or row.get("expected_missing", {})
            or derivation.get("rule") != RULE["complete_domain"] or row.get("table_seed") != 0):
        raise ValueError("Unknown complete-domain derivation")
    ids, fidelities, data = complete_domain_bytes(_file(derivation["original_source"], root), 0)
    if (derivation.get("configuration_ids") != ids or derivation.get("fidelities") != fidelities
            or _file(row["source"], root).read_bytes() != data):
        raise ValueError("Derived domain differs from all complete original configurations/bytes")
    return {"configurations": len(ids), "fidelities": fidelities, "source": derivation["original_source"],
            "derived_source": row["source"], "selection_uses_return_magnitude": False}


def verify_coverage_extension(corpus, root):
    """A new corpus cannot silently discard or reclassify original coverage."""
    if corpus.get("prior_corpus") != PRIOR or corpus.get("expected_missing_evidence") != MISSING:
        raise ValueError("V01 original corpus/missing-cell bindings differ")
    prior = read_bound_json(root, PRIOR)
    for name in ("components", "references", "optimizer_seeds", "searcher_counts",
                 "scheduler_root_count", "log_columns", "resource"):
        if corpus.get(name) != prior[name]:
            raise ValueError("V01 original case recipe was replaced")
    tables = corpus["tables"]
    if len(tables) != len(prior["tables"]) + 1:
        raise ValueError("V01 must retain all original tables and one complete-domain supplement")
    recorded = read_bound_json(root, MISSING)
    expectations = {row["case"]: row["cell"] for row in recorded["rows"] if row["side"] == "reference"}
    for current, original in zip(tables, prior["tables"]):
        if (any(current.get(key) != value for key, value in original.items())
                or current.get("role") != "original" or "derivation" in current):
            raise ValueError("V01 original table/seed/order was replaced")
        expected = {case.split("/", 1)[1]: cell for case, cell in expectations.items()
                    if case.split("/", 1)[0] == original["id"]}
        if current.get("expected_missing", {}) != expected:
            raise ValueError("V01 original missing cases were reclassified")
    original = next(row for row in prior["tables"] if row["id"] == "halfcheetah")
    supplement = tables[-1]
    if (supplement.get("id") != "halfcheetah-complete"
            or supplement.get("derivation", {}).get("original_source") != original["source"]):
        raise ValueError("V01 supplement is not the retained HalfCheetah domain")
    return verify_complete_domain(supplement, root)
