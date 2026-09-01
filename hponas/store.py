"""
Store: trial and study records with crash recovery.

Survey reference: Ch 15 sec:run-store, Ch 6 (lineage for population methods).

R1 spike: SQLite + serialized writes, crash recovery, lineage queries.
Tier 0: adds diagnostics (rung correlations), front tracking, artifact URIs.
"""

from __future__ import annotations

import json
import sqlite3
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
        self._conn.execute("PRAGMA journal_mode=WAL")  # write-ahead logging for concurrency
        self._init_schema()

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
                cost REAL NOT NULL,
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

    def write_study(self, study: Study) -> None:
        """Write a study record (upsert)."""
        self._conn.execute("""
            INSERT OR REPLACE INTO studies
            (study_id, space_json, objective, seed, budget, incumbent_value, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            study.study_id,
            study.space_json,
            study.objective,
            study.seed,
            study.budget,
            study.incumbent_value,
            study.status,
        ))
        self._conn.commit()

    def write_trial(self, trial: Trial, study_id: str) -> None:
        """Write a trial record (upsert)."""
        self._conn.execute("""
            INSERT OR REPLACE INTO trials
            (trial_id, study_id, config_json, seed, fidelity, value, cost, parent_trial_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trial.trial_id,
            study_id,
            json.dumps(trial.config),
            trial.seed,
            trial.fidelity,
            trial.value,
            trial.cost,
            trial.parent_trial_id,
            trial.status,
        ))
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
            trials.append(Trial(
                trial_id=row[0],
                config=json.loads(row[2]),
                seed=row[3],
                fidelity=row[4],
                value=row[5],
                cost=row[6],
                parent_trial_id=row[7],
                status=row[8],
            ))
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

    def write_observation(self, trial_id: str, fidelity: float, value: float, timestamp: float) -> None:
        """
        Write an intermediate observation (Tier 0: rung diagnostics for V06, V10).

        Survey: learning curves are first-class for scheduler diagnostics (Ch 5).
        Use case: V06 (ASHA cost analysis), V10 (rung correlation).
        """
        self._conn.execute("""
            INSERT INTO trial_observations (trial_id, fidelity, value, timestamp)
            VALUES (?, ?, ?, ?)
        """, (trial_id, fidelity, value, timestamp))
        self._conn.commit()

    def read_observations(self, trial_id: str) -> list[tuple[float, float, float]]:
        """
        Read all observations for a trial.

        Returns: list of (fidelity, value, timestamp) tuples.
        """
        rows = self._conn.execute("""
            SELECT fidelity, value, timestamp
            FROM trial_observations
            WHERE trial_id = ?
            ORDER BY fidelity
        """, (trial_id,)).fetchall()
        return [(row[0], row[1], row[2]) for row in rows]

    def get_pareto_front(self, study_id: str, objectives: list[str]) -> list[Trial]:
        """
        Compute Pareto front for multi-objective studies (Tier 0: V09 hypervolume tracking).

        Survey: MO methods (Ch 7) need efficient front queries for hypervolume-over-budget.

        Args:
            study_id: Study identifier
            objectives: List of objective names (for multi-objective, stored in config)

        Returns: List of non-dominated trials.

        Note: Simple O(n²) dominance check for Tier 0. Tier 1: use skyline algorithm.
        """
        trials = self.read_trials(study_id)
        if not trials:
            return []

        # Extract objective values (assume they're in trial.value for now)
        # Tier 1: extend to handle multiple objectives from config
        front = []
        for trial in trials:
            if trial.status != "completed":
                continue

            dominated = False
            for other in trials:
                if other.status != "completed" or other.trial_id == trial.trial_id:
                    continue

                # Check if other dominates trial (minimize both objectives)
                if other.value <= trial.value and other.cost <= trial.cost:
                    if other.value < trial.value or other.cost < trial.cost:
                        dominated = True
                        break

            if not dominated:
                front.append(trial)

        return front

    def write_artifact(self, trial_id: str, artifact_type: str, path: str, metadata: Optional[dict[str, Any]] = None) -> None:
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
        self._conn.execute("""
            INSERT INTO artifacts (trial_id, artifact_type, path, metadata_json)
            VALUES (?, ?, ?, ?)
        """, (trial_id, artifact_type, path, metadata_json))
        self._conn.commit()

    def read_artifacts(self, trial_id: str, artifact_type: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Read artifacts for a trial, optionally filtered by type.

        Returns: List of dicts with keys: artifact_id, artifact_type, path, metadata.
        """
        if artifact_type:
            rows = self._conn.execute("""
                SELECT artifact_id, artifact_type, path, metadata_json
                FROM artifacts
                WHERE trial_id = ? AND artifact_type = ?
            """, (trial_id, artifact_type)).fetchall()
        else:
            rows = self._conn.execute("""
                SELECT artifact_id, artifact_type, path, metadata_json
                FROM artifacts
                WHERE trial_id = ?
            """, (trial_id,)).fetchall()

        artifacts = []
        for row in rows:
            artifacts.append({
                "artifact_id": row[0],
                "artifact_type": row[1],
                "path": row[2],
                "metadata": json.loads(row[3]) if row[3] else None,
            })
        return artifacts

    def get_best_trials(self, study_id: str, n: int = 10, objective: str = "minimize") -> list[Trial]:
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

        if objective == "minimize":
            completed.sort(key=lambda t: t.value if t.value is not None else float('inf'))
        else:
            completed.sort(key=lambda t: t.value if t.value is not None else float('-inf'), reverse=True)

        return completed[:n]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
