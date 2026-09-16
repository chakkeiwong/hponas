"""Unit tests for event log infrastructure."""

import json
import tempfile
from pathlib import Path

import pytest

from hponas.events import Event, EventLog, EventType


class TestEvent:
    """Test Event dataclass serialization."""

    def test_to_dict(self):
        """Event serializes to dict correctly."""
        event = Event(
            event_id=1,
            event_type=EventType.SUGGEST,
            timestamp=1234.5,
            trial_id="trial_0",
            data={"config": {"x": 0.5}, "seed": 42}
        )

        d = event.to_dict()
        assert d["event_id"] == 1
        assert d["event_type"] == "suggest"
        assert d["timestamp"] == 1234.5
        assert d["trial_id"] == "trial_0"
        assert d["data"]["config"] == {"x": 0.5}
        assert d["data"]["seed"] == 42

    def test_from_dict(self):
        """Event deserializes from dict correctly."""
        d = {
            "event_id": 2,
            "event_type": "observe",
            "timestamp": 5678.9,
            "trial_id": "trial_1",
            "data": {"fidelity": 1.0, "value": 0.8}
        }

        event = Event.from_dict(d)
        assert event.event_id == 2
        assert event.event_type == EventType.OBSERVE
        assert event.timestamp == 5678.9
        assert event.trial_id == "trial_1"
        assert event.data["fidelity"] == 1.0
        assert event.data["value"] == 0.8

    def test_roundtrip(self):
        """Event survives to_dict -> from_dict roundtrip."""
        original = Event(
            event_id=3,
            event_type=EventType.PROMOTE,
            timestamp=9999.0,
            trial_id="trial_2",
            data={"from_fidelity": 0.25, "to_fidelity": 1.0}
        )

        d = original.to_dict()
        restored = Event.from_dict(d)

        assert restored.event_id == original.event_id
        assert restored.event_type == original.event_type
        assert restored.timestamp == original.timestamp
        assert restored.trial_id == original.trial_id
        assert restored.data == original.data


class TestEventLog:
    """Test EventLog append and query operations."""

    def test_empty_log(self):
        """Empty log initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            assert log.count() == 0
            assert log.is_empty()
            assert log.get_events() == []

    def test_record_suggest(self):
        """Suggestion events are recorded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            event = log.record_suggest(
                trial_id="trial_0",
                config={"x": 0.5, "y": 1.2},
                seed=42,
                searcher_state={"iteration": 1}
            )

            assert event.event_id == 0
            assert event.event_type == EventType.SUGGEST
            assert event.trial_id == "trial_0"
            assert event.data["config"] == {"x": 0.5, "y": 1.2}
            assert event.data["seed"] == 42
            assert event.data["searcher_state"]["iteration"] == 1

            assert log.count() == 1
            assert not log.is_empty()

    def test_record_observe(self):
        """Observation events are recorded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            event = log.record_observe(
                trial_id="trial_0",
                fidelity=1.0,
                value=0.85,
                cost=120.5
            )

            assert event.event_id == 0
            assert event.event_type == EventType.OBSERVE
            assert event.data["fidelity"] == 1.0
            assert event.data["value"] == 0.85
            assert event.data["cost"] == 120.5

    def test_multiple_events(self):
        """Multiple events maintain ordering."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            e1 = log.record_suggest("trial_0", {"x": 0.1}, seed=42)
            e2 = log.record_observe("trial_0", fidelity=1.0, value=0.8, cost=100.0)
            e3 = log.record_suggest("trial_1", {"x": 0.9}, seed=42)

            assert e1.event_id == 0
            assert e2.event_id == 1
            assert e3.event_id == 2

            events = log.get_events()
            assert len(events) == 3
            assert events[0].event_id == 0
            assert events[1].event_id == 1
            assert events[2].event_id == 2

    def test_query_by_type(self):
        """Query events by type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            log.record_suggest("trial_0", {"x": 0.1}, seed=42)
            log.record_observe("trial_0", fidelity=1.0, value=0.8, cost=100.0)
            log.record_suggest("trial_1", {"x": 0.9}, seed=42)

            suggests = log.get_suggestions()
            observes = log.get_observations()

            assert len(suggests) == 2
            assert len(observes) == 1
            assert suggests[0].data["config"]["x"] == 0.1
            assert suggests[1].data["config"]["x"] == 0.9
            assert observes[0].data["value"] == 0.8

    def test_query_by_trial(self):
        """Query events by trial_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            log.record_suggest("trial_0", {"x": 0.1}, seed=42)
            log.record_observe("trial_0", fidelity=1.0, value=0.8, cost=100.0)
            log.record_suggest("trial_1", {"x": 0.9}, seed=42)
            log.record_observe("trial_1", fidelity=1.0, value=0.7, cost=120.0)

            trial_0_events = log.get_events(trial_id="trial_0")
            trial_1_events = log.get_events(trial_id="trial_1")

            assert len(trial_0_events) == 2
            assert len(trial_1_events) == 2
            assert trial_0_events[0].trial_id == "trial_0"
            assert trial_1_events[0].trial_id == "trial_1"

    def test_persistence(self):
        """Events persist to disk and reload correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"

            # Write events
            log1 = EventLog(log_path)
            log1.record_suggest("trial_0", {"x": 0.1}, seed=42)
            log1.record_observe("trial_0", fidelity=1.0, value=0.8, cost=100.0)

            # Reload from disk
            log2 = EventLog(log_path)

            assert log2.count() == 2
            events = log2.get_events()
            assert events[0].event_type == EventType.SUGGEST
            assert events[1].event_type == EventType.OBSERVE
            assert events[0].data["config"]["x"] == 0.1
            assert events[1].data["value"] == 0.8

    def test_append_after_reload(self):
        """New events append correctly after reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"

            # Write first event
            log1 = EventLog(log_path)
            e1 = log1.record_suggest("trial_0", {"x": 0.1}, seed=42)
            assert e1.event_id == 0

            # Reload and write second event
            log2 = EventLog(log_path)
            e2 = log2.record_suggest("trial_1", {"x": 0.9}, seed=42)
            assert e2.event_id == 1

            # Verify both events present
            assert log2.count() == 2
            events = log2.get_events()
            assert events[0].event_id == 0
            assert events[1].event_id == 1

    def test_record_promote(self):
        """Promotion events are recorded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            event = log.record_promote(
                trial_id="trial_0",
                from_fidelity=0.25,
                to_fidelity=1.0,
                scheduler_state={"rung": 2}
            )

            assert event.event_type == EventType.PROMOTE
            assert event.data["from_fidelity"] == 0.25
            assert event.data["to_fidelity"] == 1.0
            assert event.data["scheduler_state"]["rung"] == 2

    def test_record_cull(self):
        """Cull events are recorded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            event = log.record_cull(
                trial_id="trial_0",
                fidelity=0.25,
                reason="bottom_quantile"
            )

            assert event.event_type == EventType.CULL
            assert event.data["fidelity"] == 0.25
            assert event.data["reason"] == "bottom_quantile"

    def test_record_checkpoint(self):
        """Checkpoint events are recorded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            event = log.record_checkpoint(
                trial_id="trial_0",
                checkpoint_path="/tmp/checkpoint_25.pkl",
                metadata={"n_trials": 25}
            )

            assert event.event_type == EventType.CHECKPOINT
            assert event.data["checkpoint_path"] == "/tmp/checkpoint_25.pkl"
            assert event.data["metadata"]["n_trials"] == 25

    def test_log_file_format(self):
        """Log file uses newline-delimited JSON format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            log = EventLog(log_path)

            log.record_suggest("trial_0", {"x": 0.1}, seed=42)
            log.record_observe("trial_0", fidelity=1.0, value=0.8, cost=100.0)

            # Verify file format
            with open(log_path, 'r') as f:
                lines = f.readlines()

            assert len(lines) == 2
            event1 = json.loads(lines[0])
            event2 = json.loads(lines[1])

            assert event1["event_type"] == "suggest"
            assert event2["event_type"] == "observe"
