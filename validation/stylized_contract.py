"""Dependency-free prospective policy for the finite stylized gates."""

STYLIZED_POLICY = {
    "version": 1,
    "decision": "D-SELF-CONTAINED-VALIDATION",
    "claim": "finite_stylized_known_answer_conformance_v1",
    "entries": ["V04-T0", "V05"],
    "counts": {"V04-T0": 1024, "V05": 128},
    "seeds": [510501, 510502],
    "trials_per_study": 16,
    "generation_wall_seconds": {"V04-T0": 300, "V05": 180},
    "reconstruction_wall_seconds_per_call": {"V04-T0": 300, "V05": 180},
    "maximum_reconstructions": 2,
    "cpu_threads": 1,
    "gpu": False,
    "freeze": "source_protocol_corpus_methods_seeds_before_first_objective",
    "oracle": "independent_analytic_and_intermediate_output_reconstruction",
    "inference": "none_no_regret_or_superiority_threshold",
    "release": "finite_correctness_only_no_searcher_or_transform_default_promotion",
    "missingness": "all_slots_retained_incomplete_is_inconclusive_no_replacement",
    "historical": "PPO_v3_pilot_sizing_and_comparison_claims_retired_prospectively",
}
