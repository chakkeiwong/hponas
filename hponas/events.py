"""
Event log infrastructure for deterministic replay (V02 requirement).

Survey reference: Ch 15 sec:run-store "event log for reproducibility"

Events capture all non-deterministic decisions in the optimization loop:
- Searcher suggestions (propose_batch calls)
- Observations reported back (report calls)
- Scheduler promotion/culling decisions
- Random number generator states

V02 Protocol: Given an event log, replaying from seed produces identical suggestions.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EventType(Enum):
    """Event types for deterministic replay."""
    SUGGEST = "suggest"
    OBSERVE = "observe"
    PROMOTE = "promote"
    CULL = "cull"
    CHECKPOINT = "checkpoint"


@dataclass
class Event:
    """
    Single event in the optimization loop.

    V02 Contract: Events must contain enough information to replay decisions.
    """
    event_id: int
    event_type: EventType
    timestamp: float
    trial_id: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "trial_id": self.trial_id,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        """Deserialize from dict."""
        return cls(
            event_id=d["event_id"],
            event_type=EventType(d["event_type"]),
            timestamp=d["timestamp"],
            trial_id=d["trial_id"],
            data=d.get("data", {}),
        )


class EventLog:
    """
    Append-only event log for deterministic replay.

    V02 Protocol Requirements:
    - All events written in order with monotonic event_id
    - Flush after each write (crash recovery)
    - Read from disk for replay
    """

    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._next_event_id = 0
        self._events: list[Event] = []
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing events from disk (crash recovery)."""
        if not self.log_path.exists():
            return

        with open(self.log_path, 'r') as f:
            for line in f:
                if line.strip():
                    event_dict = json.loads(line)
                    event = Event.from_dict(event_dict)
                    self._events.append(event)
                    self._next_event_id = max(self._next_event_id, event.event_id + 1)

    def record_suggest(
        self,
        trial_id: str,
        config: dict[str, Any],
        seed: int,
        searcher_state: Optional[dict[str, Any]] = None
    ) -> Event:
        """Record a searcher suggestion (propose_batch call).

        V02: Suggestions are the primary replay target - must be bit-identical.
        """
        event = Event(
            event_id=self._next_event_id,
            event_type=EventType.SUGGEST,
            timestamp=time.time(),
            trial_id=trial_id,
            data={
                "config": config,
                "seed": seed,
                "searcher_state": searcher_state,
            }
        )
        self._write_event(event)
        return event

    def record_observe(
        self,
        trial_id: str,
        fidelity: float,
        value: float,
        cost: float
    ) -> Event:
        """Record an observation (report call).

        V02: Observations drive subsequent suggestions - must be recorded exactly.
        """
        event = Event(
            event_id=self._next_event_id,
            event_type=EventType.OBSERVE,
            timestamp=time.time(),
            trial_id=trial_id,
            data={
                "fidelity": fidelity,
                "value": value,
                "cost": cost,
            }
        )
        self._write_event(event)
        return event

    def record_promote(
        self,
        trial_id: str,
        from_fidelity: float,
        to_fidelity: float,
        scheduler_state: Optional[dict[str, Any]] = None
    ) -> Event:
        """Record a scheduler promotion decision.

        V02 Scenario 2: ASHA promotion decisions must be deterministically replayable.
        """
        event = Event(
            event_id=self._next_event_id,
            event_type=EventType.PROMOTE,
            timestamp=time.time(),
            trial_id=trial_id,
            data={
                "from_fidelity": from_fidelity,
                "to_fidelity": to_fidelity,
                "scheduler_state": scheduler_state,
            }
        )
        self._write_event(event)
        return event

    def record_cull(
        self,
        trial_id: str,
        fidelity: float,
        reason: str
    ) -> Event:
        """Record a scheduler cull decision."""
        event = Event(
            event_id=self._next_event_id,
            event_type=EventType.CULL,
            timestamp=time.time(),
            trial_id=trial_id,
            data={
                "fidelity": fidelity,
                "reason": reason,
            }
        )
        self._write_event(event)
        return event

    def record_checkpoint(
        self,
        trial_id: str,
        checkpoint_path: str,
        metadata: Optional[dict[str, Any]] = None
    ) -> Event:
        """Record a checkpoint save (V02 Scenario 3: crash-resume).

        V02: Checkpoint events mark resume points for crash recovery.
        """
        event = Event(
            event_id=self._next_event_id,
            event_type=EventType.CHECKPOINT,
            timestamp=time.time(),
            trial_id=trial_id,
            data={
                "checkpoint_path": checkpoint_path,
                "metadata": metadata or {},
            }
        )
        self._write_event(event)
        return event

    def _write_event(self, event: Event) -> None:
        """Append event to disk (append-only, flush immediately for crash recovery)."""
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(event.to_dict()) + '\n')
            f.flush()  # Ensure durability

        self._events.append(event)
        self._next_event_id += 1

    def get_events(
        self,
        event_type: Optional[EventType] = None,
        trial_id: Optional[str] = None
    ) -> list[Event]:
        """Query events by type and/or trial_id."""
        events = self._events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if trial_id:
            events = [e for e in events if e.trial_id == trial_id]

        return events

    def get_suggestions(self) -> list[Event]:
        """Get all suggestion events (V02 replay: suggestions are the key output)."""
        return self.get_events(event_type=EventType.SUGGEST)

    def get_observations(self) -> list[Event]:
        """Get all observation events."""
        return self.get_events(event_type=EventType.OBSERVE)

    def count(self) -> int:
        """Count total events."""
        return len(self._events)

    def is_empty(self) -> bool:
        """Check if log is empty (V02 non-vacuity check)."""
        return len(self._events) == 0
