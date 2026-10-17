"""Deterministic V03 test ordering; preserve every selected pytest item.

The pinned forkserver sends an unordered set of selected node IDs to pytest.
Run the short contract layers before integration and keep each module together,
so a wiring failure is found before repeatedly starting a live worker cluster.
This plugin does not select, skip, mark or modify a test or its outcome.
"""

from collections import Counter
import os


def pytest_sessionstart(session):
    """Give each test process one CPU inside its inherited worker allocation."""
    affinity = os.sched_getaffinity(0)
    session._hponas_mutation_affinity = affinity
    cpus = sorted(affinity)
    os.sched_setaffinity(0, {cpus[os.getpid() % len(cpus)]})


def pytest_sessionfinish(session, exitstatus):
    """Restore the exact inherited envelope after the process's tests finish."""
    affinity = getattr(session, "_hponas_mutation_affinity", None)
    if affinity is not None:
        os.sched_setaffinity(0, affinity)


def order_key(nodeid):
    path = nodeid.split("::", 1)[0].removeprefix("mutants/")
    parts = path.split("/")
    layer = parts[1] if len(parts) > 2 and parts[0] == "tests" else "other"
    priority = {"unit": 0, "conformance": 1, "property": 2,
                "validation": 3, "other": 4, "integration": 5, "scale": 6}
    return priority.get(layer, 4), path, nodeid


def pytest_collection_modifyitems(items):
    before = Counter(id(item) for item in items)
    items.sort(key=lambda item: order_key(item.nodeid))
    if Counter(id(item) for item in items) != before:
        raise RuntimeError("V03 ordering changed the selected test inventory")
