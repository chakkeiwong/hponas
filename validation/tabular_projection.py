"""Declared finite-table projection for V01 engineering conformance.

This defines a new piecewise-constant benchmark over normalized coordinates.
It does not interpolate unrecorded rewards, emulate continuous PPO training,
invent runtime, or certify vendor equivalence from a nonsignificant KS test.
"""

from __future__ import annotations

import math

import numpy as np

from validation.benchmark_catalog import LandscapeTable
from validation.tier0_design import canonical_digest


class FiniteLandscapeProjection:
    """Map a unit-cube proposal to the nearest recorded physical configuration.

    Geometry uses configuration columns only. Positive log-coordinate columns
    must be explicitly declared before optimizer outcomes; other columns use
    linear coordinates. Normalize each active column by its table-domain range,
    omit constants, use squared Euclidean distance and lowest config ID on exact
    ties. Binary columns occupy 0/1. Both vendor and wrapper use the identical
    projection; the original proposal and selected ID remain in the trace.
    """

    def __init__(self, table: LandscapeTable, *, log_columns=()):
        self.table = table
        requested = tuple(log_columns)
        if len(requested) != len(set(requested)):
            raise ValueError("Duplicate log-coordinate column")
        self.ids = tuple(sorted(table.configurations))
        columns = sorted(table.configurations[self.ids[0]])
        if not set(requested) <= set(columns):
            raise ValueError("Unknown log-coordinate column")
        self.coordinates, encoded, constants = [], [], {}
        for name in columns:
            raw = [table.configurations[index][name] for index in self.ids]
            if any(type(value) is bool for value in raw) and not all(type(value) is bool for value in raw):
                raise ValueError("Column mixes boolean and numeric configurations")
            binary = all(type(value) is bool for value in raw)
            if name in requested and (binary or min(raw) <= 0):
                raise ValueError("Log coordinates require a positive numeric domain")
            transform = "log" if name in requested else "linear"
            values = np.asarray([math.log(value) if transform == "log" else float(value) for value in raw])
            low, high = float(values.min()), float(values.max())
            if low == high:
                constants[name] = raw[0]
                continue
            span = high - low
            if not math.isfinite(span):
                raise ValueError("Nonfinite configuration geometry")
            self.coordinates.append({"column": name, "transform": transform, "binary": binary,
                                     "transformed_low": low, "transformed_high": high})
            encoded.append((values - low) / span)
        if not encoded:
            raise ValueError("Table has no varying configuration coordinate")
        self.points = np.asarray(encoded, dtype=float).T
        self.specification = {
            "kind": "declared_nearest_configuration_table_projection", "schema_version": 1,
            "table_sha256": table.sha256, "configuration_ids": list(self.ids),
            "coordinates": self.coordinates, "constants": constants,
            "distance": "squared_euclidean_unit_coordinates", "tie_break": "lowest_config_id",
            "domain": "closed_unit_cube", "missing_cells": "retain_original_status_no_imputation",
            "cost_kind": "not_recorded", "scope": "projected finite table, not original continuous workload",
        }
        self.digest = canonical_digest(self.specification)

    def project(self, proposal):
        raw = np.asarray(proposal)
        if (raw.dtype.kind not in "iuf" or raw.shape != (len(self.coordinates),)
                or not np.isfinite(raw).all() or (raw < 0).any() or (raw > 1).any()):
            raise ValueError("Finite unit-cube proposal with exact coordinate count required")
        values = raw.astype(float)
        distances = np.square(self.points - values).sum(axis=1)
        position = int(np.argmin(distances))
        return {"proposal": values.tolist(), "config_id": self.ids[position],
                "physical_config": dict(self.table.configurations[self.ids[position]]),
                "squared_distance": float(distances[position]), "projection_digest": self.digest}

    def evaluate(self, proposal, *, seed, training_steps):
        projected = self.project(proposal)
        return {**self.table.lookup(projected["config_id"], seed, training_steps), **projected,
                "evaluation_kind": "recorded_cell_after_declared_projection", "interpolated": False,
                "certifies_acceptance": False}
