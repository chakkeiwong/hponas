"""
SearchSpace: schema for mixed continuous/ordinal/categorical knobs with transforms and conditions.

Survey reference: Ch 15 (contracts), Ch 2 (knob kinds).
Corrected knob-kind semantics: three typed kinds (continuous, ordinal, categorical),
conditionality is structural (lives in the `condition` field).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import numpy as np

KnobKind = Literal["continuous", "ordinal", "categorical"]
Transform = Literal["log", "logit", "none"]


@dataclass
class Knob:
    """
    One hyperparameter declaration.

    Attributes:
        name: identifier
        kind: continuous | ordinal | categorical (three typed kinds per Ch 15)
        bounds: (low, high) for continuous/ordinal, or list of values for categorical
        transform: optional warping (log-uniform for scale-type knobs per Ch 3)
        condition: optional parent-knob predicate (makes the space a tree, not a box)
        prior: optional expert belief (consumed by πBO/PriorBand in T1, inert before)
        note: free text for units and meaning (documentation)
    """
    name: str
    kind: KnobKind
    bounds: tuple[float, float] | list[Any]
    transform: Transform = "none"
    condition: Optional[tuple[str, Any]] = None  # (parent_name, parent_value)
    prior: Optional[dict[str, Any]] = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind in ["continuous", "ordinal"]:
            if not isinstance(self.bounds, tuple) or len(self.bounds) != 2:
                raise ValueError(f"{self.name}: continuous/ordinal requires (low, high) bounds")
            low, high = self.bounds
            if low >= high:
                raise ValueError(f"{self.name}: bounds {self.bounds} invalid (low >= high)")
        elif self.kind == "categorical":
            if not isinstance(self.bounds, list) or len(self.bounds) < 2:
                raise ValueError(f"{self.name}: categorical requires list of >=2 values")

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to a JSON-safe dict.

        Tuples (bounds for continuous/ordinal, condition pairs) become lists, since JSON
        has no tuple type; `from_dict` restores them. Round-tripping through this pair is
        lossless for the fields the schema contract covers.
        """
        return {
            "name": self.name,
            "kind": self.kind,
            "bounds": list(self.bounds),
            "transform": self.transform,
            "condition": list(self.condition) if self.condition is not None else None,
            "prior": self.prior,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Knob":
        """
        Rebuild a Knob from `to_dict` output.

        Restores tuple types that JSON flattened to lists: continuous/ordinal bounds and
        the (parent_name, parent_value) condition pair. Categorical bounds stay a list,
        which is what `__post_init__` requires.
        """
        kind = data["kind"]
        bounds = data["bounds"]
        if kind in ("continuous", "ordinal"):
            bounds = tuple(bounds)
        else:
            bounds = list(bounds)

        condition = data.get("condition")
        if condition is not None:
            condition = tuple(condition)

        return cls(
            name=data["name"],
            kind=kind,
            bounds=bounds,
            transform=data.get("transform", "none"),
            condition=condition,
            prior=data.get("prior"),
            note=data.get("note", ""),
        )


@dataclass
class SearchSpace:
    """
    Tree of knob declarations with conditional structure.

    Survey contract (Ch 15 sec:search-space-schema): the schema tracks knob kinds,
    conditional structure, and optional priors. Three typed kinds, not four; the
    fourth (conditional) is structural.
    """
    knobs: list[Knob] = field(default_factory=list)

    def add_knob(self, knob: Knob) -> None:
        """Add a knob to the space."""
        if any(k.name == knob.name for k in self.knobs):
            raise ValueError(f"Duplicate knob name: {knob.name}")
        if knob.condition:
            parent_name, _ = knob.condition
            if not any(k.name == parent_name for k in self.knobs):
                raise ValueError(
                    f"{knob.name}: condition references unknown parent {parent_name}"
                )
        self.knobs.append(knob)

    def sample_config(self, rng: np.random.Generator) -> dict[str, Any]:
        """
        Sample one configuration from the space (unconditional uniform/log-uniform).
        Conditional knobs: sampled only when their parent condition holds.
        """
        config: dict[str, Any] = {}
        for knob in self.knobs:
            if knob.condition:
                parent_name, parent_value = knob.condition
                if config.get(parent_name) != parent_value:
                    continue  # condition not met, skip this knob

            if knob.kind == "continuous":
                low, high = knob.bounds
                if knob.transform == "log":
                    val = np.exp(rng.uniform(np.log(low), np.log(high)))
                else:
                    val = rng.uniform(low, high)
                config[knob.name] = float(val)
            elif knob.kind == "ordinal":
                low, high = knob.bounds
                config[knob.name] = int(rng.integers(low, high + 1))
            elif knob.kind == "categorical":
                config[knob.name] = rng.choice(knob.bounds)
        return config

    def validate_config(self, config: dict[str, Any]) -> None:
        """
        Check that a configuration satisfies the space constraints.
        Raises ValueError if invalid.
        """
        for knob in self.knobs:
            self._check_presence(knob, config)
            if knob.name in config:
                self._check_value(knob, config[knob.name])

    def _check_presence(self, knob: Knob, config: dict[str, Any]) -> None:
        """
        Check that a knob is present exactly when its condition allows it.

        A conditional knob exists only when its predicate holds (Ch 2, Ch 15); a value
        supplied for a knob whose predicate fails is a meaningless coordinate, not a
        harmless extra.
        """
        if knob.condition is None:
            if knob.name not in config:
                raise ValueError(f"{knob.name}: missing from config")
            return

        parent_name, parent_value = knob.condition
        condition_holds = config.get(parent_name) == parent_value

        if condition_holds and knob.name not in config:
            raise ValueError(f"{knob.name}: required when {parent_name}={parent_value}")
        if not condition_holds and knob.name in config:
            raise ValueError(
                f"{knob.name}: must not be set when {parent_name}!={parent_value}"
            )

    def _check_value(self, knob: Knob, val: Any) -> None:
        """Check one value against its knob's kind and bounds."""
        if knob.kind == "continuous":
            low, high = knob.bounds
            if not (low <= val <= high):
                raise ValueError(f"{knob.name}: {val} out of bounds [{low}, {high}]")
        elif knob.kind == "ordinal":
            low, high = knob.bounds
            if not (isinstance(val, int) and low <= val <= high):
                raise ValueError(f"{knob.name}: {val} not an integer in [{low}, {high}]")
        elif knob.kind == "categorical":
            if val not in knob.bounds:
                raise ValueError(f"{knob.name}: {val} not in {knob.bounds}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the space to a JSON-safe dict."""
        return {"knobs": [k.to_dict() for k in self.knobs]}

    def to_json(self) -> str:
        """
        Serialize the space to canonical JSON for the run store's `Study.space_json`.

        The schema is the contract (Ch 15), so the serialized form has to be readable by
        anything that queries the store — warm start compares a prior study's space
        against the current one. Keys are sorted so the same space always produces the
        same string.
        """
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchSpace":
        """Rebuild a space from `to_dict` output."""
        return cls(knobs=[Knob.from_dict(k) for k in data.get("knobs", [])])

    @classmethod
    def from_json(cls, text: str) -> "SearchSpace":
        """
        Rebuild a space from `to_json` output.

        Raises json.JSONDecodeError on malformed input and ValueError/KeyError if the
        payload is well-formed JSON but not a space (callers that treat deserialization
        as best-effort should catch these).
        """
        return cls.from_dict(json.loads(text))
