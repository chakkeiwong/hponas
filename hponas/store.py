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
            CREATE INDEX IF NOT EXISTS idx_trials_study ON trials(study_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trials_parent ON trials(parent_trial_id)
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

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
