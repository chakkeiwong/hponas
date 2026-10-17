"""The execution-order repair must preserve selection and be deterministic."""

from itertools import permutations
from types import SimpleNamespace

from tools.v03_test_order import pytest_collection_modifyitems
from tools import v03_test_order
import pytest


def test_all_input_orders_preserve_the_same_exact_test_objects_in_one_fixed_order():
    names = ["tests/integration/test_ray.py::test_a",
             "tests/unit/test_ray.py::test_b[2]",
             "tests/integration/test_ray.py::test_b",
             "tests/unit/test_ray.py::test_a",
             "tests/conformance/test_executor.py::test_public"]
    source = [SimpleNamespace(nodeid=name) for name in names]
    expected = [source[3], source[1], source[4], source[0], source[2]]
    for sequence in permutations(source):
        items = list(sequence)
        pytest_collection_modifyitems(items)
        assert [id(item) for item in items] == [id(item) for item in expected]


def test_no_test_is_deduplicated_or_removed_for_empty_repeated_or_unknown_nodes():
    duplicate = SimpleNamespace(nodeid="custom/location.py::test_x")
    for items in [[], [duplicate], [duplicate, duplicate]]:
        before = list(items)
        pytest_collection_modifyitems(items)
        assert items == before


@pytest.mark.parametrize("cpus,pid,selected", [({7}, 29, 7), ({2, 4, 7, 9}, 11, 9), ({2, 4, 7, 9}, 12, 2)])
def test_test_process_pins_inside_inherited_allocation_and_restores_it(monkeypatch, cpus, pid, selected):
    changes = []
    monkeypatch.setattr(v03_test_order.os, "sched_getaffinity", lambda target: cpus)
    monkeypatch.setattr(v03_test_order.os, "getpid", lambda: pid)
    monkeypatch.setattr(v03_test_order.os, "sched_setaffinity", lambda target, value: changes.append((target, value)))
    session = SimpleNamespace()
    v03_test_order.pytest_sessionstart(session)
    assert changes == [(0, {selected})]
    v03_test_order.pytest_sessionfinish(session, 1)
    assert changes == [(0, {selected}), (0, cpus)]


def test_affinity_failure_is_visible_before_tests_start(monkeypatch):
    monkeypatch.setattr(v03_test_order.os, "sched_getaffinity", lambda target: {1})
    def refuse(*args):
        raise PermissionError("affinity unavailable")
    monkeypatch.setattr(v03_test_order.os, "sched_setaffinity", refuse)
    with pytest.raises(PermissionError, match="affinity unavailable"):
        v03_test_order.pytest_sessionstart(SimpleNamespace())
