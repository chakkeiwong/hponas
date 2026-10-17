"""Public persistence must retain identities and the exact sampler position."""

import json
from types import SimpleNamespace

import pytest
from scipy.stats import qmc

from hponas import events
from hponas.searchers.random_searcher import SobolSearcher
from hponas.space import Knob, SearchSpace


def test_all_public_event_records_round_trip_and_extend_one_ordered_log(tmp_path, monkeypatch):
    stamps = iter([100., 101., 102., 103., 104., 105.])
    monkeypatch.setattr(events, "time", SimpleNamespace(time=lambda: next(stamps)))
    path = tmp_path / "events.jsonl"
    log = events.EventLog(path)
    recorded = [
        log.record_suggest("a", {"x": 1}, 19),
        log.record_observe("a", 1, 5, 2),
        log.record_promote("a", 1, 2),
        log.record_cull("b", 1, "quality floor"),
        log.record_checkpoint("b", "policy.json"),
    ]
    persisted = [json.loads(line) for line in path.read_text().splitlines()]
    assert persisted == [record.to_dict() for record in recorded]
    assert [row["event_id"] for row in persisted] == list(range(5))
    assert [row["timestamp"] for row in persisted] == [100., 101., 102., 103., 104.]
    assert [row["trial_id"] for row in persisted] == ["a", "a", "a", "b", "b"]
    restored = events.EventLog(path)
    assert [event.event_type for event in restored.get_events(trial_id="b")] == [
        events.EventType.CULL, events.EventType.CHECKPOINT]
    assert restored.get_events(trial_id="b")[-1].data == {
        "checkpoint_path": "policy.json", "metadata": {}}
    appended = restored.record_checkpoint("a", "continued.json", {"step": 2})
    assert (appended.event_id, appended.timestamp, appended.trial_id) == (5, 105., "a")
    assert len(events.EventLog(path).get_events()) == 6


def test_event_without_optional_payload_reconstructs_an_empty_mapping():
    record = events.Event.from_dict({"event_id": 0, "event_type": "checkpoint",
                                     "timestamp": 100., "trial_id": "a"})
    assert record.data == {}
    assert json.loads(json.dumps(record.to_dict()))["data"] == {}


@pytest.mark.parametrize("scramble", [False, True])
@pytest.mark.parametrize("consumed", [0, 1, 5])
def test_sobol_checkpoint_continues_independent_sequence_at_exact_position(scramble, consumed):
    space = SearchSpace([Knob("x", "continuous", (-2., 3.)), Knob("y", "continuous", (0., 1.))])
    source = SobolSearcher(space, seed=19, scramble=scramble)
    for _ in range(consumed):
        source.suggest()
    state = json.loads(json.dumps(source.get_state()))
    restored = SobolSearcher(space, seed=97, scramble=not scramble)
    restored.set_state(state)
    oracle = qmc.Sobol(d=2, seed=19, scramble=scramble).random_base2(4)[consumed:consumed + 3]
    for x, y in oracle:
        assert restored.suggest().values == pytest.approx({"x": -2. + 5. * x, "y": y})
    assert restored.get_state()["sample_count"] == consumed + 3
