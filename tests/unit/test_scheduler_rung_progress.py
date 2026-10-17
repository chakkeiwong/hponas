"""Finite rung construction must either advance or refuse its numeric inputs."""

from contextlib import contextmanager
import math
import signal

import pytest

from hponas.schedulers import (
    ASHAConfig, ASHAScheduler, BudgetedASHAConfig, BudgetedASHAScheduler,
    MOASHAConfig, MOASHAScheduler, PASHAConfig, PASHAScheduler,
)


@contextmanager
def construction_deadline():
    # Constructor-only safety net: prevent a nonadvancing loop exhausting RAM.
    # The ordinary constructor takes microseconds; no workload is timed here.
    def expired(signum, frame):
        raise AssertionError("Rung construction did not terminate")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 1.)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.)
        signal.signal(signal.SIGALRM, previous)


@pytest.fixture(params=[
    (ASHAConfig, ASHAScheduler, {}),
    (BudgetedASHAConfig, BudgetedASHAScheduler, {}),
    (PASHAConfig, PASHAScheduler, {}),
    (MOASHAConfig, MOASHAScheduler, {"objectives": ["loss", "cost"]}),
], ids=["asha", "budgeted", "pasha", "mo"])
def build_scheduler(request):
    config_type, scheduler_type, options = request.param

    def build(eta, r_min, r_max):
        return scheduler_type(config_type(eta=eta, r_min=r_min, r_max=r_max, **options))

    return build


def test_nonadvancing_subnormal_rung_is_refused(build_scheduler):
    smallest = math.ulp(0.)
    eta = math.nextafter(1., math.inf)
    # All config inequalities hold, but represented multiplication cannot advance.
    assert eta > 1. and smallest > 0. and smallest * eta == smallest
    with construction_deadline(), pytest.raises(ValueError, match="strictly increase"):
        build_scheduler(eta, smallest, 2 * smallest)


@pytest.mark.parametrize("eta,low,high,expected", [
    (3., 1., 27., [1., 3., 9., 27.]),
    (3., 1., 10., [1., 3., 9., 10.]),
    (2., 2., 2., [2.]),
    (3., 1e308, 1.5e308, [1e308, 1.5e308]),
    (2., math.ulp(0.), 4 * math.ulp(0.),
     [math.ulp(0.), 2 * math.ulp(0.), 4 * math.ulp(0.)]),
    (math.nextafter(1., math.inf), math.ulp(0.), math.ulp(0.), [math.ulp(0.)]),
])
def test_rungs_include_exact_terminal_budget_without_duplicates(build_scheduler, eta, low, high, expected):
    with construction_deadline():
        scheduler = build_scheduler(eta, low, high)
    assert scheduler.rungs == expected
    assert all(left < right for left, right in zip(scheduler.rungs, scheduler.rungs[1:]))
