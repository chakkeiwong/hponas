"""Offline, provenance-bound benchmark inspection for STAT-03.

Reading external landscape data is not an HPO campaign. In particular, a
recorded extreme is neither an objective support bound nor an attained score
on the project's live PPO recipe. Missing cells remain missing.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def verify_source_bundle(manifest_path):
    """Verify exact bytes before interpreting downloaded, untrusted sources."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("kind") != "benchmark-source-bundle" or manifest.get("schema_version") != 1:
        raise ValueError("Unknown benchmark source bundle")
    sources = manifest.get("sources", [])
    if not sources:
        raise ValueError("Empty benchmark source bundle")
    root, result = manifest_path.parent.resolve(), {}
    for source in sources:
        name = source["path"]
        path = (root / name).resolve()
        if (not isinstance(name, str) or not path.is_relative_to(root)
                or path == root or name in result or not source.get("url", "").startswith("https://")
                or not source.get("revision")):
            raise ValueError("Invalid, duplicate or unpinned benchmark source")
        data = path.read_bytes()
        if len(data) != source.get("bytes") or hashlib.sha256(data).hexdigest() != source.get("sha256"):
            raise ValueError(f"Changed benchmark source: {name}")
        result[name] = path
    return result


def _positive_int(value, name, *, zero=False):
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError(f"Invalid {name}")
    return value


class LandscapeTable:
    """Exact finite ARLBench lookup; never interpolate off-table suggestions.

    Keys are (config_id, recorded RL seed, training steps). These are external
    RL runs, not independent HPO study replicates. There is no measured runtime
    column, so this adapter deliberately cannot produce a cost receipt.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.cells = {}
        self.configurations = {}
        self.seeds = set()
        self.training_steps = set()
        with self.path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            names = reader.fieldnames or []
            if (len(names) != len(set(names))
                    or not {"config_id", "seed", "training_steps", "performance"} <= set(names)):
                raise ValueError("Missing or duplicate landscape columns")
            knobs = sorted(n for n in names if n.startswith("hp_config."))
            if not knobs:
                raise ValueError("Landscape has no physical configurations")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Malformed landscape row")
                config_id = _positive_int(int(row["config_id"]), "config ID", zero=True)
                seed = _positive_int(int(row["seed"]), "seed", zero=True)
                steps = _positive_int(int(row["training_steps"]), "training steps")
                config = {}
                for name in knobs:
                    raw = row[name]
                    value = raw == "True" if raw in {"True", "False"} else float(raw)
                    if not isinstance(value, bool) and not math.isfinite(value):
                        raise ValueError("Nonfinite physical configuration")
                    config[name] = value
                if config_id in self.configurations and self.configurations[config_id] != config:
                    raise ValueError("Configuration changes across seeds/fidelities")
                self.configurations[config_id] = config
                key = config_id, seed, steps
                if key in self.cells:
                    raise ValueError("Duplicate landscape cell")
                raw = row["performance"].strip()
                value = float(raw) if raw else None
                status = "blank" if value is None else ("finite" if math.isfinite(value) else "nonfinite")
                self.cells[key] = {"status": status, "value": value if status == "finite" else None}
                self.seeds.add(seed)
                self.training_steps.add(steps)
        if not self.cells:
            raise ValueError("Empty landscape")

    def lookup(self, config_id, seed, training_steps):
        key = (_positive_int(config_id, "config ID", zero=True),
               _positive_int(seed, "seed", zero=True),
               _positive_int(training_steps, "training steps"))
        if key not in self.cells:
            raise ValueError("No recorded cell; off-table interpolation is forbidden")
        return {"config_id": config_id, "seed": seed, "training_steps": training_steps,
                **self.cells[key], "source_sha256": self.sha256,
                "cost_seconds": None, "cost_kind": "not_recorded",
                "certifies_acceptance": False}

    def profile(self):
        terminal = max(self.training_steps)
        terminal_cells = [self.cells.get((c, s, terminal), {"status": "absent", "value": None})
                          for c in sorted(self.configurations) for s in sorted(self.seeds)]
        counts = Counter(cell["status"] for cell in terminal_cells)
        finite = sorted(cell["value"] for cell in terminal_cells if cell["status"] == "finite")
        expected = len(self.configurations) * len(self.seeds) * len(self.training_steps)
        by_step = []
        for step in sorted(self.training_steps):
            statuses = Counter(self.cells.get((c, s, step), {"status": "absent"})["status"]
                               for c in self.configurations for s in self.seeds)
            by_step.append({"training_steps": step, "statuses": dict(sorted(statuses.items()))})
        return {
            "source_sha256": self.sha256, "rows": len(self.cells),
            "configurations": len(self.configurations), "seeds": sorted(self.seeds),
            "training_steps": sorted(self.training_steps),
            "absent_grid_cells": expected - len(self.cells), "fidelities": by_step,
            "terminal_training_steps": terminal, "terminal_expected_cells": len(terminal_cells),
            "terminal_statuses": dict(sorted(counts.items())),
            "terminal_missing_fraction": 1 - len(finite) / len(terminal_cells),
            "terminal_finite_min": min(finite) if finite else None,
            "terminal_finite_max": max(finite) if finite else None,
            "scale_adopted": False, "provides_population_support_bound": False,
            "independent_hpo_studies": 0, "cost_seconds": None,
        }


def lcbench_instances(config_space_path, encoding_path):
    """The configuration domain owns eligibility; embedding-only IDs do not."""
    space = json.loads(Path(config_space_path).read_text())
    encoding = json.loads(Path(encoding_path).read_text())["OpenML_task_id"]
    parameters = space["hyperparameters"]
    matches = [p for p in parameters if p["name"] == "OpenML_task_id"]
    if len(matches) != 1 or matches[0].get("type") != "categorical":
        raise ValueError("Unrecognized LCBench instance domain")
    instances = matches[0]["choices"]
    if (not instances or len(instances) != len(set(instances))
            or any(not isinstance(i, str) or not i.isdecimal() or i not in encoding for i in instances)):
        raise ValueError("Invalid or unencoded LCBench task ID")
    return {"instances": sorted(instances, key=int),
            "encoding_only_ids": sorted(set(encoding) - set(instances) - {"#na#"}, key=int),
            "sampling_unit": "source_dataset_not_task_id_or_fold",
            "supports_live_ppo_claim": False, "certifies_acceptance": False}


def arlbench_ppo_universe(dataset_metadata_path):
    """Enumerate source filenames without using optimizer performance."""
    meta = json.loads(Path(dataset_metadata_path).read_text())
    names = [item["rfilename"] for item in meta["siblings"]]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate dataset filenames")
    return sorted(name for name in names if name.startswith("landscapes/") and name.endswith("_ppo.csv"))
