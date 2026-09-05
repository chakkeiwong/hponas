"""
Test the confirmatory statistics core.

Survey reference: Ch 16 (validation). Authority: `validation/protocols.json` `policy`.
Every test below pins one rule the register declares, so a drift in the implementation
shows up as a failing test rather than as a quietly different decision.
"""

import numpy as np
import pytest

from validation.stats import (
    DEFAULT_ALPHA,
    MISSINGNESS_VOID_FRACTION,
    BootstrapResult,
    Cluster,
    MissingnessReport,
    PairedBlock,
    ScaleBounds,
    build_clusters,
    cluster_level_mean,
    holm_bonferroni,
    non_inferiority_one_sided,
    paired_cluster_bootstrap,
    simulate_power,
    size_by_simulation,
    superiority_one_sided,
    variance_upper_bound,
)


# ---------------------------------------------------------------------------
# Scale bounds
# ---------------------------------------------------------------------------


def test_scale_bounds_span():
    assert ScaleBounds(low=0.0, high=4.0).span == 4.0


def test_scale_bounds_rejects_degenerate_range():
    with pytest.raises(ValueError, match="must exceed"):
        ScaleBounds(low=1.0, high=1.0)
    with pytest.raises(ValueError, match="must exceed"):
        ScaleBounds(low=2.0, high=1.0)


def test_scale_bounds_rejects_unknown_direction():
    with pytest.raises(ValueError, match="unknown direction"):
        ScaleBounds(low=0.0, high=1.0, direction="whatever")  # type: ignore[arg-type]


def test_normalized_difference_minimize_sign_flip():
    """On a minimized objective a lower arm value is an improvement (positive)."""
    bounds = ScaleBounds(low=0.0, high=10.0, direction="minimize")
    assert bounds.normalized_difference(arm_value=3.0, comparator_value=5.0) == 0.2
    assert bounds.normalized_difference(arm_value=5.0, comparator_value=3.0) == -0.2


def test_normalized_difference_maximize_no_flip():
    bounds = ScaleBounds(low=0.0, high=10.0, direction="maximize")
    assert bounds.normalized_difference(arm_value=5.0, comparator_value=3.0) == 0.2


def test_normalized_difference_divides_by_declared_span_not_baseline():
    """The denominator is the frozen span, so a near-zero baseline is not a problem."""
    bounds = ScaleBounds(low=-1.0, high=1.0, direction="minimize")
    # A percentage difference against comparator 0.0 would be undefined.
    assert bounds.normalized_difference(arm_value=-0.5, comparator_value=0.0) == 0.25


# ---------------------------------------------------------------------------
# Blocks, clusters, missingness
# ---------------------------------------------------------------------------


def test_paired_block_complete():
    assert PairedBlock("t", 0, 1.0, 2.0).complete
    assert not PairedBlock("t", 0, None, 2.0).complete
    assert not PairedBlock("t", 0, 1.0, None).complete
    assert not PairedBlock("t", 0, None, None).complete


def test_build_clusters_groups_by_task():
    bounds = {
        "a": ScaleBounds(low=0.0, high=1.0),
        "b": ScaleBounds(low=0.0, high=1.0),
    }
    blocks = [
        PairedBlock("a", 0, 0.4, 0.5),
        PairedBlock("a", 1, 0.3, 0.5),
        PairedBlock("b", 0, 0.9, 0.8),
    ]
    clusters, report = build_clusters(blocks, bounds)

    assert [c.task for c in clusters] == ["a", "b"]
    np.testing.assert_allclose(clusters[0].differences, [0.1, 0.2])
    np.testing.assert_allclose(clusters[1].differences, [-0.1])
    assert report.planned == 3
    assert report.complete == 3
    assert report.loss_fraction == 0.0
    assert not report.voids_campaign


def test_build_clusters_excludes_incomplete_block_whole():
    """An unpaired replicate is dropped with its pairing, not half-used."""
    bounds = {"a": ScaleBounds(low=0.0, high=1.0)}
    blocks = [
        PairedBlock("a", 0, 0.4, 0.5),
        PairedBlock("a", 1, None, 0.5),
    ]
    clusters, report = build_clusters(blocks, bounds)

    assert clusters[0].n_blocks == 1
    assert report.complete == 1
    assert report.dropped == (("a", 1),)
    assert report.loss_fraction == 0.5
    assert report.voids_campaign


def test_build_clusters_requires_declared_bounds():
    with pytest.raises(KeyError, match="No declared scale bounds"):
        build_clusters([PairedBlock("unregistered", 0, 1.0, 2.0)], {})


def test_missingness_void_threshold_is_strict():
    """Exactly 10% loss does not void; above 10% does (policy.missingness)."""
    at_limit = MissingnessReport(planned=10, complete=9, dropped=(("a", 0),))
    assert at_limit.loss_fraction == pytest.approx(MISSINGNESS_VOID_FRACTION)
    assert not at_limit.voids_campaign

    over = MissingnessReport(planned=10, complete=8, dropped=(("a", 0), ("a", 1)))
    assert over.voids_campaign


def test_missingness_report_empty_plan():
    report = MissingnessReport(planned=0, complete=0, dropped=())
    assert report.loss_fraction == 0.0
    assert not report.voids_campaign


def test_missingness_report_to_dict():
    report = MissingnessReport(planned=4, complete=3, dropped=(("a", 7),))
    d = report.to_dict()
    assert d["planned"] == 4
    assert d["complete"] == 3
    assert d["dropped"] == [{"task": "a", "seed": 7}]
    assert d["loss_fraction"] == pytest.approx(0.25)
    assert d["voids_campaign"] is True


def test_cluster_level_mean_weights_tasks_equally():
    """A task with many replicates does not outvote a task with few."""
    clusters = [
        Cluster("many", np.array([0.0] * 100)),
        Cluster("few", np.array([1.0])),
    ]
    assert cluster_level_mean(clusters) == pytest.approx(0.5)


def test_cluster_level_mean_requires_clusters():
    with pytest.raises(ValueError, match="no clusters"):
        cluster_level_mean([])


# ---------------------------------------------------------------------------
# Paired cluster bootstrap
# ---------------------------------------------------------------------------


def _uniform_clusters(effect: float, n_clusters: int = 4, n_blocks: int = 6) -> list[Cluster]:
    rng = np.random.default_rng(0)
    return [
        Cluster(f"task_{i}", rng.normal(effect, 0.05, size=n_blocks))
        for i in range(n_clusters)
    ]


def test_bootstrap_shape_and_point():
    clusters = _uniform_clusters(0.1)
    boot = paired_cluster_bootstrap(clusters, draws=500, seed=1)

    assert boot.replicates.shape == (500,)
    assert boot.draws == 500
    assert boot.n_clusters == 4
    assert boot.n_blocks == 24
    assert boot.point == pytest.approx(cluster_level_mean(clusters))


def test_bootstrap_is_deterministic_under_seed():
    clusters = _uniform_clusters(0.1)
    a = paired_cluster_bootstrap(clusters, draws=200, seed=7)
    b = paired_cluster_bootstrap(clusters, draws=200, seed=7)
    c = paired_cluster_bootstrap(clusters, draws=200, seed=8)

    np.testing.assert_array_equal(a.replicates, b.replicates)
    assert not np.array_equal(a.replicates, c.replicates)


def test_bootstrap_rejects_empty_and_nonpositive_draws():
    with pytest.raises(ValueError, match="no clusters"):
        paired_cluster_bootstrap([], draws=10)
    with pytest.raises(ValueError, match="draws must be positive"):
        paired_cluster_bootstrap(_uniform_clusters(0.1), draws=0)


def test_bootstrap_spread_grows_with_between_task_variance():
    """Between-task disagreement widens the interval; that is why tasks are the outer unit."""
    tight = [Cluster(f"t{i}", np.full(6, 0.1)) for i in range(4)]
    spread = [Cluster(f"t{i}", np.full(6, v)) for i, v in enumerate([-0.3, 0.0, 0.2, 0.5])]

    tight_boot = paired_cluster_bootstrap(tight, draws=2000, seed=3)
    spread_boot = paired_cluster_bootstrap(spread, draws=2000, seed=3)

    assert tight_boot.replicates.std() < spread_boot.replicates.std()


def test_bootstrap_single_block_clusters_still_resample_tasks():
    """With one replicate per task the only variation left is which tasks are drawn."""
    clusters = [Cluster(f"t{i}", np.array([v])) for i, v in enumerate([0.0, 0.4])]
    boot = paired_cluster_bootstrap(clusters, draws=1000, seed=2)

    assert set(np.unique(boot.replicates)).issubset({0.0, 0.2, 0.4})
    assert boot.replicates.std() > 0.0


def test_confidence_bounds_bracket_the_point():
    boot = paired_cluster_bootstrap(_uniform_clusters(0.2), draws=2000, seed=5)
    assert boot.lower_bound(0.05) < boot.point < boot.upper_bound(0.05)


def test_one_sided_p_is_never_zero():
    """Finite draws cannot prove a bound, so p is floored at 1/(draws+1)."""
    boot = paired_cluster_bootstrap(_uniform_clusters(5.0), draws=100, seed=0)
    p = boot.one_sided_p(0.0)
    assert p > 0.0
    assert p == pytest.approx(1.0 / 101.0)


def test_one_sided_p_saturates_when_effect_is_absent():
    boot = paired_cluster_bootstrap(_uniform_clusters(-5.0), draws=100, seed=0)
    assert boot.one_sided_p(0.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# One-sided decisions
# ---------------------------------------------------------------------------


def test_superiority_detects_a_real_gain():
    result = superiority_one_sided("V11a", _uniform_clusters(0.25), margin=0.0, draws=2000, seed=1)

    assert result.test == "superiority_one_sided"
    assert result.threshold == 0.0
    assert result.point > 0.0
    assert result.clears(DEFAULT_ALPHA)
    assert result.p_value < DEFAULT_ALPHA


def test_superiority_does_not_fire_on_noise():
    """A null effect must not clear: this is the false-positive direction that matters."""
    rng = np.random.default_rng(11)
    clusters = [Cluster(f"t{i}", rng.normal(0.0, 0.2, size=5)) for i in range(4)]
    result = superiority_one_sided("V11a", clusters, margin=0.0, draws=2000, seed=1)

    assert not result.clears(DEFAULT_ALPHA)
    assert result.p_value > DEFAULT_ALPHA


def test_superiority_honors_a_nonzero_margin():
    clusters = _uniform_clusters(0.05)
    assert superiority_one_sided("x", clusters, margin=0.0, draws=2000, seed=1).clears(DEFAULT_ALPHA)
    assert not superiority_one_sided("x", clusters, margin=0.2, draws=2000, seed=1).clears(
        DEFAULT_ALPHA
    )


def test_non_inferiority_threshold_is_minus_margin():
    result = non_inferiority_one_sided("V11b", _uniform_clusters(0.0), margin=0.1, draws=500, seed=1)
    assert result.test == "non_inferiority_one_sided"
    assert result.threshold == pytest.approx(-0.1)


def test_non_inferiority_accepts_a_tolerated_shortfall():
    """A 2% shortfall clears a 10% margin: worse, but inside the product tolerance."""
    result = non_inferiority_one_sided(
        "V11b", _uniform_clusters(-0.02), margin=0.1, draws=2000, seed=1
    )
    assert result.point < 0.0
    assert result.clears(DEFAULT_ALPHA)


def test_non_inferiority_rejects_a_shortfall_past_the_margin():
    result = non_inferiority_one_sided(
        "V11b", _uniform_clusters(-0.3), margin=0.1, draws=2000, seed=1
    )
    assert not result.clears(DEFAULT_ALPHA)


def test_non_inferiority_requires_positive_margin():
    with pytest.raises(ValueError, match="margin must be positive"):
        non_inferiority_one_sided("V11b", _uniform_clusters(0.0), margin=0.0)


def test_test_result_to_dict_records_the_alpha_used():
    result = superiority_one_sided("V11a", _uniform_clusters(0.25), draws=500, seed=1)
    d = result.to_dict(alpha=0.0125)

    assert d["entry_id"] == "V11a"
    assert d["test"] == "superiority_one_sided"
    assert d["alpha_used"] == 0.0125
    assert d["threshold"] == 0.0
    assert d["n_clusters"] == 4
    assert d["n_blocks"] == 24
    assert d["draws"] == 500
    assert d["lower_bound"] == pytest.approx(result.lower_bound(0.0125))
    assert d["clears"] is result.clears(0.0125)


def test_a_stricter_alpha_is_harder_to_clear():
    clusters = _uniform_clusters(0.06)
    result = superiority_one_sided("x", clusters, draws=4000, seed=2)
    assert result.lower_bound(0.05) > result.lower_bound(0.0083)


# ---------------------------------------------------------------------------
# Holm-Bonferroni
# ---------------------------------------------------------------------------


def test_holm_orders_by_p_value_and_relaxes_alpha():
    decisions = holm_bonferroni({"a": 0.04, "b": 0.001, "c": 0.02}, alpha=0.05)

    assert [d.entry_id for d in decisions] == ["b", "c", "a"]
    assert [d.rank for d in decisions] == [1, 2, 3]
    assert decisions[0].adjusted_alpha == pytest.approx(0.05 / 3)
    assert decisions[1].adjusted_alpha == pytest.approx(0.05 / 2)
    assert decisions[2].adjusted_alpha == pytest.approx(0.05)


def test_holm_step_down_stops_at_the_first_failure():
    """Once a member fails, larger p-values fail too even if under their own alpha."""
    decisions = holm_bonferroni({"a": 0.03, "b": 0.04, "c": 0.049}, alpha=0.05)
    assert [d.reject for d in decisions] == [False, False, False]


def test_holm_rejects_everything_when_all_p_are_small():
    decisions = holm_bonferroni({"a": 0.001, "b": 0.002}, alpha=0.05)
    assert all(d.reject for d in decisions)


def test_holm_corrects_for_the_declared_family_not_the_subset_run():
    """The tier-1 gate declares six members; running two still corrects for six."""
    two_of_six = holm_bonferroni({"V11a": 0.012, "V11b": 0.02}, alpha=0.05, family_size=6)
    assert two_of_six[0].adjusted_alpha == pytest.approx(0.05 / 6)
    assert not two_of_six[0].reject

    uncorrected = holm_bonferroni({"V11a": 0.012, "V11b": 0.02}, alpha=0.05)
    assert uncorrected[0].adjusted_alpha == pytest.approx(0.05 / 2)
    assert uncorrected[0].reject


def test_holm_decision_to_dict():
    decision = holm_bonferroni({"V11a": 0.001}, alpha=0.05, family_size=6)[0]
    assert decision.to_dict() == {
        "entry_id": "V11a",
        "p_value": 0.001,
        "rank": 1,
        "adjusted_alpha": pytest.approx(0.05 / 6),
        "reject": True,
    }


def test_holm_rejects_family_size_below_tests_supplied():
    with pytest.raises(ValueError, match="smaller than"):
        holm_bonferroni({"a": 0.01, "b": 0.02}, family_size=1)


def test_holm_rejects_nonpositive_family_size():
    with pytest.raises(ValueError, match="family_size must be positive"):
        holm_bonferroni({}, family_size=0)


def test_holm_on_empty_family_is_empty():
    assert holm_bonferroni({}) == []


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------


def test_variance_upper_bound_exceeds_the_point_estimate():
    values = [0.1, 0.2, 0.15, 0.3, 0.05]
    s2 = float(np.var(values, ddof=1))
    assert variance_upper_bound(values) > s2


def test_variance_upper_bound_tightens_with_more_data():
    rng = np.random.default_rng(0)
    small = rng.normal(0.0, 1.0, size=5)
    large = rng.normal(0.0, 1.0, size=200)
    ratio_small = variance_upper_bound(small) / float(np.var(small, ddof=1))
    ratio_large = variance_upper_bound(large) / float(np.var(large, ddof=1))
    assert ratio_large < ratio_small


def test_variance_upper_bound_input_guards():
    with pytest.raises(ValueError, match="at least 2 observations"):
        variance_upper_bound([1.0])
    with pytest.raises(ValueError, match="confidence must be in"):
        variance_upper_bound([1.0, 2.0], confidence=1.0)


def test_simulate_power_rises_with_effect_size():
    common = dict(
        cluster_sd=0.05,
        block_sd=0.1,
        n_clusters=4,
        blocks_per_cluster=6,
        threshold=0.0,
        alpha=0.05,
        replicates=200,
        draws=199,
        seed=0,
    )
    weak = simulate_power(effect=0.02, **common)
    strong = simulate_power(effect=0.30, **common)
    assert strong > weak
    assert strong > 0.8


def test_simulate_power_at_the_null_is_near_alpha():
    """Under no effect the rule should fire at roughly its nominal rate, not routinely."""
    power = simulate_power(
        effect=0.0,
        cluster_sd=0.05,
        block_sd=0.1,
        n_clusters=5,
        blocks_per_cluster=6,
        threshold=0.0,
        alpha=0.05,
        replicates=400,
        draws=199,
        seed=1,
    )
    assert power < 0.25


def test_simulate_power_rises_with_sample_size():
    common = dict(
        effect=0.08,
        cluster_sd=0.06,
        block_sd=0.15,
        n_clusters=5,
        threshold=0.0,
        alpha=0.05,
        replicates=200,
        draws=199,
        seed=2,
    )
    assert simulate_power(blocks_per_cluster=12, **common) >= simulate_power(
        blocks_per_cluster=2, **common
    )


def test_simulate_power_input_guard():
    with pytest.raises(ValueError, match="at least one cluster"):
        simulate_power(
            effect=0.1,
            cluster_sd=0.1,
            block_sd=0.1,
            n_clusters=0,
            blocks_per_cluster=4,
            threshold=0.0,
            alpha=0.05,
        )


def test_size_by_simulation_picks_the_smallest_adequate_n():
    result = size_by_simulation(
        effect=0.30,
        cluster_sd=0.05,
        block_sd=0.1,
        n_clusters=4,
        threshold=0.0,
        alpha=0.05,
        power_target=0.8,
        max_sample=20,
        candidates=[2, 5, 10],
        replicates=200,
        draws=199,
        seed=0,
    )
    assert result.reaches_target
    assert result.chosen_n == 2
    assert result.attained_power >= 0.8
    # Search stops at the first adequate size instead of walking the whole grid.
    assert len(result.curve) == 1


def test_size_by_simulation_reports_inconclusive_at_the_cap():
    """Hitting max_sample without power is a real outcome (policy.power.max_sample_rule)."""
    result = size_by_simulation(
        effect=0.001,
        cluster_sd=0.5,
        block_sd=0.5,
        n_clusters=3,
        threshold=0.0,
        alpha=0.05,
        power_target=0.8,
        max_sample=4,
        candidates=[2, 4],
        replicates=100,
        draws=99,
        seed=0,
    )
    assert not result.reaches_target
    assert result.chosen_n is None
    assert [n for n, _ in result.curve] == [2, 4]


def test_size_by_simulation_clips_candidates_to_max_sample():
    result = size_by_simulation(
        effect=0.001,
        cluster_sd=0.5,
        block_sd=0.5,
        n_clusters=3,
        threshold=0.0,
        alpha=0.05,
        power_target=0.99,
        max_sample=3,
        candidates=[2, 3, 50],
        replicates=50,
        draws=99,
        seed=0,
    )
    assert [n for n, _ in result.curve] == [2, 3]


def test_size_by_simulation_rejects_an_empty_grid():
    with pytest.raises(ValueError, match="empty candidate grid"):
        size_by_simulation(
            effect=0.1,
            cluster_sd=0.1,
            block_sd=0.1,
            n_clusters=3,
            threshold=0.0,
            alpha=0.05,
            power_target=0.8,
            max_sample=10,
            candidates=[50, 60],
        )


def test_sizing_result_to_dict():
    result = size_by_simulation(
        effect=0.30,
        cluster_sd=0.05,
        block_sd=0.1,
        n_clusters=4,
        threshold=0.0,
        alpha=0.05,
        power_target=0.8,
        max_sample=20,
        candidates=[2],
        replicates=100,
        draws=99,
        seed=0,
    )
    d = result.to_dict()
    assert d["power_target"] == 0.8
    assert d["max_sample"] == 20
    assert d["curve"] == [{"blocks_per_cluster": 2, "power": result.attained_power}]
    assert d["reaches_target"] is result.reaches_target


def test_bootstrap_result_is_usable_standalone():
    """The dataclass carries its own bounds so reports do not recompute quantiles."""
    boot = BootstrapResult(
        point=0.1,
        replicates=np.linspace(0.0, 1.0, 1001),
        draws=1001,
        n_clusters=3,
        n_blocks=9,
    )
    assert boot.lower_bound(0.05) == pytest.approx(0.05, abs=1e-3)
    assert boot.upper_bound(0.05) == pytest.approx(0.95, abs=1e-3)
