"""
Store: trial and study records with crash recovery.

Survey reference: Ch 15 sec:run-store, Ch 6 (lineage for population methods).

R1 spike: SQLite + serialized writes, crash recovery, lineage queries.
Tier 0: adds diagnostics (rung correlations), front tracking, artifact URIs.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class Trial:
    """
    One trial record (Ch 15 contract).

    Survey: trial rows carry config, seed, rung history, learning curve, final objectives,
    veto outcomes, and parent pointer (population lineage).
    """

    trial_id: str
    config: dict[str, Any]
    seed: int
    fidelity: float
    value: float
    cost: float  # wall-clock seconds
    parent_trial_id: Optional[str] = None  # population lineage
    status: str = "running"  # running | completed | stopped


@dataclass
class Study:
    """
    One study record (Ch 15 contract).

    Survey: study rows carry the declaration (space, objective, seeds, budget),
    incumbent over time, and study-level diagnostics.
    """

    study_id: str
    space_json: str  # serialized SearchSpace
    objective: str  # minimize | maximize
    seed: int
    budget: float  # total compute budget
    incumbent_value: Optional[float] = None
    status: str = "running"


class Store:
    """
    SQLite store with crash recovery (Ch 15 contract, R1 spike requirement).

    Survey verdict: storage technology is an engineering judgment; the schema is the contract.

    Spike: SQLite with WAL mode, serialized writes, lineage queries.
    Tier 0: add rung correlation diagnostics (V06), hypervolume-over-budget (V09), warm-start ranked query (V12).
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        try:
            # A simultaneous first opener can make the journal-mode transition
            # return SQLITE_BUSY immediately, bypassing SQLite's busy timeout.
            # Bound retries of this idempotent transition as well as SQLite waits.
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
                    break
                except sqlite3.OperationalError as exc:
                    code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
                    if (
                        code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                        or time.monotonic() >= deadline
                    ):
                        raise
                    time.sleep(0.01)
            self._init_schema()
        except BaseException:
            self._conn.close()
            raise

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS studies (
                study_id TEXT PRIMARY KEY,
                space_json TEXT NOT NULL,
                objective TEXT NOT NULL,
                seed INTEGER NOT NULL,
                budget REAL NOT NULL,
                incumbent_value REAL,
                status TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trials (
                trial_id TEXT PRIMARY KEY,
                study_id TEXT NOT NULL,
                config_json TEXT NOT NULL,
                seed INTEGER NOT NULL,
                fidelity REAL NOT NULL,
                value REAL,
                cost REAL,
                parent_trial_id TEXT,
                status TEXT NOT NULL,
                FOREIGN KEY(study_id) REFERENCES studies(study_id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trial_observations (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                trial_id TEXT NOT NULL,
                fidelity REAL NOT NULL,
                value REAL NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY(trial_id) REFERENCES trials(trial_id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                trial_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                path TEXT NOT NULL,
                metadata_json TEXT,
                FOREIGN KEY(trial_id) REFERENCES trials(trial_id)
            )
        """)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS study_snapshots (study_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS trial_objectives (trial_id TEXT PRIMARY KEY, values_json TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS warm_history (study_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trials_study ON trials(study_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trials_parent ON trials(parent_trial_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_trial ON trial_observations(trial_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_artifacts_trial ON artifacts(trial_id)
        """)
        self._conn.commit()

    def save_study_snapshot(self, state):
        """Commit the authoritative ledger and query projections in one transaction."""
        eligible = [r for r in state["results"].values() if r["status"] == "completed"]
        if state.get("scheduler_state"):
            eligible = [
                r
                for r in eligible
                if r["fidelity"] == state["scheduler_state"]["config"]["r_max"]
            ]
        incumbent = (max if state["maximize"] else min)(
            (r["objective_value"] for r in eligible), default=None
        )
        vector_contract = state.get("multi_objective")
        if vector_contract is not None:
            from hponas.multi_objective import ObjectiveSpec
            from hponas.types import Result

            spec = ObjectiveSpec(**vector_contract["contract"])
            if vector_contract["identity"] != spec.identity:
                raise ValueError("Store objective contract identity differs")
            for row in state["results"].values():
                spec.validate_result(Result(**row))
            incumbent = None
        status = state.get("outcome") or ("completed" if state.get("finished") else "running")
        evaluation = state.get("evaluation")
        if evaluation is not None:
            from hponas.evaluation import evaluation_outcome
            final_outcome = evaluation_outcome(evaluation)
            if final_outcome != 'completed':
                status = 'evaluation_' + final_outcome
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO study_snapshots VALUES (?, ?)",
                (state["study_name"], json.dumps(state)),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO studies VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    state["study_name"],
                    json.dumps(state["space"]),
                    "multi_objective" if vector_contract else "maximize" if state["maximize"] else "minimize",
                    state["searcher_state"].get("seed") or 0,
                    state["budget"],
                    incumbent,
                    status,
                ),
            )
            for tid, trial in state["trials"].items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO trials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tid,
                        state["study_name"],
                        json.dumps(trial["config"]["values"]),
                        trial["seed"] or 0,
                        trial["fidelity"],
                        None if vector_contract else trial["value"],
                        trial["cost"],
                        trial["parent_trial_id"],
                        trial["status"],
                    ),
                )
                from hponas.persistence import snapshot_artifacts
                self._conn.execute("DELETE FROM artifacts WHERE trial_id=?", (tid,))
                for kind, path in snapshot_artifacts(state, tid):
                    if isinstance(path, str):
                        self._conn.execute(
                            "INSERT INTO artifacts(trial_id,artifact_type,path) VALUES (?,?,?)",
                            (tid, kind, path),
                        )

    def load_study_snapshot(self, study_id):
        row = self._conn.execute(
            "SELECT payload FROM study_snapshots WHERE study_id=?", (study_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def read_evaluation(self, study_id):
        """Read declared roles and raw repetitions, including the separate final ledger.

        Search history and warm-start queries continue to use tuning results.
        The caller is responsible for access to this reporting surface.
        """
        state = self.load_study_snapshot(study_id)
        if state is None:
            return None
        if state.get("evaluation") is None:
            from hponas.evaluation import legacy_evaluation_report
            return legacy_evaluation_report(state.get('legacy_reason'))
        return state["evaluation"]

    def read_rung_diagnostics(self, study_id):
        """Reconstruct observed-pair ranks from the authoritative tuning ledger."""
        from hponas.diagnostics import read_rung_diagnostics
        return read_rung_diagnostics(self.load_study_snapshot(study_id))

    def read_report(self, study_id):
        from hponas.reporting import study_report
        return study_report(self.load_study_snapshot(study_id))

    def export_report(self, study_id, destination):
        from hponas.reporting import export_study_report
        return export_study_report(self.load_study_snapshot(study_id), destination)

    def freeze_warm_history(self, study_id, *, task_id, model_family, task_domain,
                            objective_key, endpoint_fidelity=1.0):
        """Retain completed history atomically with an observed completion cutoff.

        Call after the study has completed. The snapshot is immutable even if
        live study rows later change. Legacy rows without explicit metadata are
        never inferred to be eligible. No retrospective completion date is guessed.
        """
        from dataclasses import asdict
        from .space import SearchSpace
        from .warm_history import _finite, _identity, canonical, digest, space_signature

        identity = {"study_id": study_id, "task_id": task_id, "model_family": model_family,
                    "task_domain": task_domain, "objective_key": objective_key,
                    "endpoint_fidelity": endpoint_fidelity}
        _identity({**identity, "direction": "minimize"})
        if not _finite(endpoint_fidelity) or endpoint_fidelity <= 0:
            raise ValueError("A positive finite endpoint fidelity is required")
        if self._conn.in_transaction:
            raise ValueError("History freeze requires its own transaction")
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            previous = self._conn.execute(
                "SELECT payload FROM warm_history WHERE study_id=?", (study_id,)
            ).fetchone()
            if previous:
                retained = json.loads(previous[0])
                body = {k: v for k, v in retained.items() if k != "binding"}
                if retained.get("binding") != digest(body):
                    raise ValueError("Retained warm history binding differs")
                if any(retained.get(k) != v for k, v in identity.items()):
                    raise ValueError("Completed history identity is immutable")
                return retained
            study = self.read_study(study_id)
            if study is None or study.status != "completed":
                raise ValueError("Only a completed stored study can become warm history")
            trials = [asdict(t) for t in self.read_trials(study_id)]
            if any(t["status"] in {"pending", "running", "paused"} for t in trials):
                raise ValueError("Completed history cannot contain unfinished trials")
            # Retain invalid outcomes with an explicit disposition; SQLite's
            # nullable/nonfinite measurements must not become ranked observations.
            for trial in trials:
                if trial["status"] == "completed" and not _finite(trial["value"]):
                    trial.update(status="nonfinite", value=None)
                for key in ["cost", "value"]:
                    if trial[key] is not None and not _finite(trial[key]):
                        trial[key] = None
            body = {**identity, "direction": study.objective,
                    "space_signature": space_signature(SearchSpace.from_json(study.space_json)),
                    "status": "completed", "completed_at": time.time(), "trials": trials,
                    "schema": "warm_history_snapshot_v1"}
            _identity(body)
            retained = {**body, "binding": digest(body)}
            self._conn.execute("INSERT INTO warm_history VALUES (?, ?)",
                               (study_id, canonical(retained)))
        return retained

    def read_warm_histories(self):
        """Read complete immutable history rows in one SQLite read snapshot."""
        from .warm_history import digest

        rows = self._conn.execute("SELECT study_id,payload FROM warm_history ORDER BY study_id").fetchall()
        records = []
        for sid, payload in rows:
            value = json.loads(payload)
            body = {k: v for k, v in value.items() if k != "binding"}
            if (value.get("binding") != digest(body) or value.get("study_id") != sid
                    or value.get("schema") != "warm_history_snapshot_v1"):
                raise ValueError("Retained warm history binding differs")
            records.append(value)
        return records

    def write_study(self, study: Study) -> None:
        """Write a study record (upsert)."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO studies
            (study_id, space_json, objective, seed, budget, incumbent_value, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                study.study_id,
                study.space_json,
                study.objective,
                study.seed,
                study.budget,
                study.incumbent_value,
                study.status,
            ),
        )
        self._conn.commit()

    def write_trial(self, trial: Trial, study_id: str) -> None:
        """Write a trial record (upsert)."""
        if trial.trial_id is None or trial.trial_id == "":
            raise ValueError("trial_id cannot be None or empty")

        self._conn.execute(
            """
            INSERT OR REPLACE INTO trials
            (trial_id, study_id, config_json, seed, fidelity, value, cost, parent_trial_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                trial.trial_id,
                study_id,
                json.dumps(trial.config),
                trial.seed,
                trial.fidelity,
                trial.value,
                trial.cost,
                trial.parent_trial_id,
                trial.status,
            ),
        )
        self._conn.commit()

    def read_study(self, study_id: str) -> Optional[Study]:
        """Read a study record by ID."""
        row = self._conn.execute(
            "SELECT * FROM studies WHERE study_id = ?", (study_id,)
        ).fetchone()
        if row is None:
            return None
        return Study(
            study_id=row[0],
            space_json=row[1],
            objective=row[2],
            seed=row[3],
            budget=row[4],
            incumbent_value=row[5],
            status=row[6],
        )

    def read_trials(self, study_id: str) -> list[Trial]:
        """Read all trials for a study."""
        rows = self._conn.execute(
            "SELECT * FROM trials WHERE study_id = ? ORDER BY trial_id", (study_id,)
        ).fetchall()
        trials = []
        for row in rows:
            trials.append(
                Trial(
                    trial_id=row[0],
                    config=json.loads(row[2]),
                    seed=row[3],
                    fidelity=row[4],
                    value=row[5],
                    cost=row[6],
                    parent_trial_id=row[7],
                    status=row[8],
                )
            )
        return trials

    def lineage(self, trial_id: str) -> list[str]:
        """
        Return the lineage of a trial (Ch 15: parent pointer makes schedules a first-class output).
        Survey: with the parent pointer, a hyperparameter schedule is a walk up the tree.
        """
        path = []
        current = trial_id
        while current:
            path.append(current)
            row = self._conn.execute(
                "SELECT parent_trial_id FROM trials WHERE trial_id = ?", (current,)
            ).fetchone()
            if row is None or row[0] is None:
                break
            current = row[0]
        return path

    def write_observation(
        self, trial_id: str, fidelity: float, value: float, timestamp: float
    ) -> None:
        """
        Write an intermediate observation (Tier 0: rung diagnostics for V06, V10).

        Survey: learning curves are first-class for scheduler diagnostics (Ch 5).
        Use case: V06 (ASHA cost analysis), V10 (rung correlation).
        """
        self._conn.execute(
            """
            INSERT INTO trial_observations (trial_id, fidelity, value, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (trial_id, fidelity, value, timestamp),
        )
        self._conn.commit()

    def read_observations(self, trial_id: str) -> list[tuple[float, float, float]]:
        """
        Read all observations for a trial.

        Returns: list of (fidelity, value, timestamp) tuples.
        """
        rows = self._conn.execute(
            """
            SELECT fidelity, value, timestamp
            FROM trial_observations
            WHERE trial_id = ?
            ORDER BY fidelity
        """,
            (trial_id,),
        ).fetchall()
        return [(row[0], row[1], row[2]) for row in rows]

    def write_objectives(self, trial_id: str, values: dict[str, float]) -> None:
        """Store named objective measurements separately from search parameters."""
        import math

        if not values or not all(math.isfinite(v) for v in values.values()):
            raise ValueError("Objective measurements must be nonempty and finite")
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO trial_objectives VALUES (?,?)",
                (trial_id, json.dumps(values)),
            )

    def get_pareto_front(
        self, study_id: str, objectives: list[str], directions=None
    ) -> list[Trial]:
        """Return the completed nondominated trials for the requested measurements.

        Directions default to minimization; provide one 'minimize'/'maximize'
        per objective. Scalar 'value' and measured 'cost' remain available.
        """
        import numpy as np

        snapshot = self.load_study_snapshot(study_id)
        if snapshot and snapshot.get("multi_objective") is not None:
            from hponas.multi_objective import ObjectiveSpec
            from hponas.types import Result

            spec = ObjectiveSpec(**snapshot["multi_objective"]["contract"])
            if snapshot["multi_objective"]["identity"] != spec.identity:
                raise ValueError("Stored metric identity differs")
            expected_directions = ["minimize" if o["direction"] == "min" else "maximize" for o in spec.contract["objectives"]]
            if objectives != spec.names or (directions is not None and directions != expected_directions):
                raise ValueError("Query must match the frozen objective names and directions")
            endpoint = snapshot["scheduler_state"]["config"]["r_max"] if snapshot.get("scheduler_state") else 1.
            summary = spec.summarize([Result(**r) for r in snapshot["results"].values()], endpoint_fidelity=endpoint)
            return [Trial(trial_id=tid, config=snapshot["trials"][tid]["config"]["values"],
                          seed=snapshot["trials"][tid]["seed"], fidelity=snapshot["trials"][tid]["fidelity"],
                          value=None, cost=snapshot["trials"][tid]["cost"],
                          parent_trial_id=snapshot["trials"][tid]["parent_trial_id"], status=snapshot["trials"][tid]["status"])
                    for tid in summary["front_trial_ids"]]
        if not objectives or len(set(objectives)) != len(objectives):
            raise ValueError("Specify unique objective names")
        directions = directions or ["minimize"] * len(objectives)
        if len(directions) != len(objectives) or any(
            d not in ("minimize", "maximize") for d in directions
        ):
            raise ValueError("One direction per objective is required")
        trials = [t for t in self.read_trials(study_id) if t.status == "completed"]
        measurements = dict(
            self._conn.execute(
                "SELECT trial_id,values_json FROM trial_objectives"
            ).fetchall()
        )
        vectors = []
        for trial in trials:
            values = {
                "value": trial.value,
                "cost": trial.cost,
                **json.loads(measurements.get(trial.trial_id, "{}")),
            }
            try:
                y = np.array([values[name] for name in objectives], dtype=float)
            except KeyError as exc:
                raise ValueError(
                    f"Missing objective {exc} for {trial.trial_id}"
                ) from exc
            if not np.isfinite(y).all():
                raise ValueError(f"Nonfinite objective for {trial.trial_id}")
            vectors.append(
                y * np.array([1 if d == "minimize" else -1 for d in directions])
            )
        return [
            t
            for i, t in enumerate(trials)
            if not any(
                np.all(y <= vectors[i]) and np.any(y < vectors[i])
                for j, y in enumerate(vectors)
                if i != j
            )
        ]

    def write_artifact(
        self,
        trial_id: str,
        artifact_type: str,
        path: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Register an artifact (checkpoint, model, plot) for a trial (Tier 0: V12, V14 requirements).

        Survey: artifact tracking (Ch 15) enables checkpoint reuse (V12 warm start) and
        reproducibility (V14 day-one walk artifacts).

        Args:
            trial_id: Trial identifier
            artifact_type: Type of artifact (checkpoint | model | plot | log)
            path: Filesystem path or URI
            metadata: Optional metadata dict
        """
        metadata_json = json.dumps(metadata) if metadata else None
        self._conn.execute(
            """
            INSERT INTO artifacts (trial_id, artifact_type, path, metadata_json)
            VALUES (?, ?, ?, ?)
        """,
            (trial_id, artifact_type, path, metadata_json),
        )
        self._conn.commit()

    def read_artifacts(
        self, trial_id: str, artifact_type: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Read artifacts for a trial, optionally filtered by type.

        Returns: List of dicts with keys: artifact_id, artifact_type, path, metadata.
        """
        if artifact_type:
            rows = self._conn.execute(
                """
                SELECT artifact_id, artifact_type, path, metadata_json
                FROM artifacts
                WHERE trial_id = ? AND artifact_type = ?
            """,
                (trial_id, artifact_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT artifact_id, artifact_type, path, metadata_json
                FROM artifacts
                WHERE trial_id = ?
            """,
                (trial_id,),
            ).fetchall()

        artifacts = []
        for row in rows:
            artifacts.append(
                {
                    "artifact_id": row[0],
                    "artifact_type": row[1],
                    "path": row[2],
                    "metadata": json.loads(row[3]) if row[3] else None,
                }
            )
        return artifacts

    def get_best_trials(
        self, study_id: str, n: int = 10, objective: str = "minimize"
    ) -> list[Trial]:
        """
        Get top-n trials for a study (Tier 0: V12 warm-start query).

        Survey: warm start (V12) queries the store for similar completed studies.

        Args:
            study_id: Study identifier
            n: Number of trials to return
            objective: minimize | maximize

        Returns: List of trials sorted by value (best first).
        """
        trials = self.read_trials(study_id)
        completed = [t for t in trials if t.status == "completed"]

        study = self.read_study(study_id)
        if study is not None and study.objective == "multi_objective":
            raise ValueError("Multi-objective studies require a Pareto query")
        if objective == "minimize":
            completed.sort(
                key=lambda t: t.value if t.value is not None else float("inf")
            )
        else:
            completed.sort(
                key=lambda t: t.value if t.value is not None else float("-inf"),
                reverse=True,
            )

        return completed[:n]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def list_studies(self) -> list[Study]:
        """
        List all studies in the store (Tier 2: cross-study warm start query).

        Survey: V12 warm start from "similar completed studies," plural. A Tier 2 helper
        queries all studies, filters by `check_space_compatibility`, and loads best trials
        from any compatible study, not just one named study_id.

        Returns: All studies, newest first.
        """
        rows = self._conn.execute("""
            SELECT study_id, space_json, objective, seed, budget, incumbent_value, status
            FROM studies
            ORDER BY ROWID DESC
        """).fetchall()
        return [
            Study(
                study_id=row[0],
                space_json=row[1],
                objective=row[2],
                seed=row[3],
                budget=row[4],
                incumbent_value=row[5],
                status=row[6],
            )
            for row in rows
        ]
