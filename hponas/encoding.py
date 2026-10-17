"""Shared normalized coordinates for the public Knob and legacy Parameter schemas.

Categoricals use stable enumerated coordinates. Inactive coordinates are neutral;
the parent coordinate distinguishes branches and decoding removes inactive keys.
"""

from __future__ import annotations

import numpy as np
from hponas.space import Knob, SearchSpace


def as_knob_space(space):
    if isinstance(space, SearchSpace):
        return space
    if not hasattr(space, "parameters"):
        raise TypeError("Expected a Knob or Parameter SearchSpace")
    knobs = []
    for name, parameter in space.parameters.items():
        kind = {"integer": "ordinal", "discrete": "categorical"}.get(
            parameter.type.value, parameter.type.value
        )
        bounds = (
            list(parameter.choices)
            if kind == "categorical"
            else tuple(parameter.bounds)
        )
        knobs.append(
            Knob(name, kind, bounds, transform="log" if parameter.log_scale else "none")
        )
    return SearchSpace(knobs)


class SpaceEncoder:
    def __init__(self, space):
        self.space = as_knob_space(space)

    @staticmethod
    def _warp(value, transform):
        if transform == "log":
            return np.log(value)
        if transform == "logit":
            return np.log(value / (1 - value))
        return value

    def encode(self, config):
        values = (
            config.values
            if hasattr(config, "values") and not isinstance(config, dict)
            else config
        )
        self.space.validate_config(values)
        encoded = []
        for knob in self.space.knobs:
            if knob.name not in values:
                encoded.append(0.5)
            elif knob.kind == "categorical":
                encoded.append(knob.bounds.index(values[knob.name]) / len(knob.bounds))
            else:
                low, high = (self._warp(v, knob.transform) for v in knob.bounds)
                encoded.append(
                    (self._warp(values[knob.name], knob.transform) - low) / (high - low)
                )
        return np.asarray(encoded, dtype=float)

    def decode(self, coordinates, sampling=False):
        if len(coordinates) != len(self.space.knobs):
            raise ValueError("Coordinate dimension does not match search space")
        values = {}
        for knob, raw in zip(self.space.knobs, coordinates):
            if knob.condition and values.get(knob.condition[0]) != knob.condition[1]:
                continue
            u = float(np.clip(raw, 0.0, 1.0))
            if not np.isfinite(u):
                raise ValueError("Coordinates must be finite")
            if knob.kind == "categorical":
                index = (
                    int(u * len(knob.bounds))
                    if sampling
                    else round(u * len(knob.bounds))
                )
                value = knob.bounds[min(index, len(knob.bounds) - 1)]
            else:
                lo, hi = knob.bounds
                low, high = (self._warp(v, knob.transform) for v in knob.bounds)
                value = low + u * (high - low)
                if knob.transform == "log":
                    value = np.exp(value)
                elif knob.transform == "logit":
                    value = 1 / (1 + np.exp(-value))
                if knob.kind == "ordinal":
                    value = (
                        int(lo + u * (hi - lo + 1))
                        if sampling and knob.transform == "none"
                        else round(value)
                    )
                    value = int(np.clip(value, lo, hi))
                else:
                    value = float(np.clip(value, lo, hi))
            values[knob.name] = value
        self.space.validate_config(values)
        return values
