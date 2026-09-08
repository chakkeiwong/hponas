#!/usr/bin/env python3
"""
Rebuild product_register.json with full traceability fields.

Extends current product_register.json with:
- latex_ref: LaTeX file and line numbers
- impl_file: Implementation file path
- test_file: Test file path(s)
- status: ✓ match | ❌ violation | ⚠️ missing | 🔀 deferred

Satisfies: Week 1 Day 4-6 deliverable (TRACEABILITY_MATRIX_v1.md requirement)
Authority: BUILD_PROGRAM_REVIEW_VERDICT.md finding B9 (malformed register)
"""

import json
from pathlib import Path
from typing import Any

# Traceability mapping from TRACEABILITY_MATRIX_v1.md analysis
TRACEABILITY = {
    "roadmap-01": {
        "latex_ref": "03-model-free.tex:89-124",
        "impl_file": "hponas/searchers.py:45-98",
        "test_file": "tests/test_space.py:89-145; tests/test_schedulers_tier0.py:12-45",
        "status": "✓",
    },
    "roadmap-02": {
        "latex_ref": "03-model-free.tex:73-88",
        "impl_file": "hponas/searchers.py:101-135",
        "test_file": "tests/test_schedulers_tier0.py:48-67",
        "status": "✓",
    },
    "roadmap-03": {
        "latex_ref": "05-multifidelity.tex:234-289",
        "impl_file": "hponas/schedulers.py:45-289",
        "test_file": "tests/test_schedulers.py:23-178; tests/test_mo_asha.py:15-89",
        "status": "✓",
        "notes": "PASHA flag missing (minor)",
    },
    "roadmap-04": {
        "latex_ref": "04-bayesian.tex:467-521",
        "impl_file": "hponas/searchers_tpe.py:1-187",
        "test_file": "tests/test_schedulers_tier0.py:70-102",
        "status": "✓",
    },
    "roadmap-05": {
        "latex_ref": "04-bayesian.tex:522-866",
        "impl_file": "hponas/searchers_gp.py:1-466",
        "test_file": "tests/test_schedulers_tier0.py:105-189; tests/test_priors.py:18-56",
        "status": "✓",
        "notes": "πBO correctly implemented in log-space (lines 351-466)",
    },
    "roadmap-06": {
        "latex_ref": "04-bayesian.tex:864-866",
        "impl_file": "hponas/searchers_gp.py:87-95",
        "test_file": "tests/test_priors.py:59-78",
        "status": "✓",
    },
    "roadmap-07": {
        "latex_ref": "07-multiobjective.tex:268-401",
        "impl_file": "hponas/searchers_mo.py:41-289",
        "test_file": "tests/test_reporting_mo.py:18-92; tests/test_nsgaii.py:89-145",
        "status": "✓",
    },
    "roadmap-08": {
        "latex_ref": "07-multiobjective.tex:527-568",
        "impl_file": "hponas/searchers_mo.py:294-443",
        "test_file": "tests/test_reporting_mo.py:95-134",
        "status": "✓",
    },
    "roadmap-09": {
        "latex_ref": "07-multiobjective.tex:568-622",
        "impl_file": "hponas/schedulers.py:292-456",
        "test_file": "tests/test_mo_asha.py:92-234",
        "status": "✓",
    },
    "roadmap-10": {
        "latex_ref": "08-priors-transfer.tex:14-91,368-384",
        "impl_file": "hponas/priors.py:1-199; hponas/searchers_priorband.py:1-198; hponas/searchers_gp.py:351-466",
        "test_file": "tests/test_priors.py:81-234; tests/test_prior_recovery_pibo.py:18-134",
        "status": "✓",
        "notes": "Both πBO and PriorBand correctly implemented",
    },
    "roadmap-11": {
        "latex_ref": "08-priors-transfer.tex:93-142,385-390",
        "impl_file": "hponas/warm_start.py:1-303",
        "test_file": "tests/test_warm_start.py:15-189",
        "status": "✓",
        "notes": "Ranked query correct; RGPE correctly deferred (second wave)",
    },
    "roadmap-12": {
        "latex_ref": "08-priors-transfer.tex:396-403",
        "impl_file": "hponas/searchers_cost.py:1-356",
        "test_file": "tests/test_cost_aware.py:18-145; tests/test_cost_efficiency.py:15-98",
        "status": "✓",
    },
    "roadmap-13": {
        "latex_ref": "06-population.tex:357-498",
        "impl_file": "",
        "test_file": "",
        "status": "⚠️",
        "notes": "T2.4 not yet implemented (8 days, blocked by T2.1-T2.3)",
    },
    "roadmap-14": {
        "latex_ref": "05-multifidelity.tex:497-503",
        "impl_file": "",
        "test_file": "",
        "status": "⚠️",
        "notes": "T3 elective, V07 gate required before implementation",
    },
    "roadmap-15": {
        "latex_ref": "05-multifidelity.tex:279-306,507-528; 08-priors-transfer.tex:391-395",
        "impl_file": "",
        "test_file": "",
        "status": "❌",
        "notes": "T3 elective; use pretrained surrogate, do NOT build custom model",
    },
    "roadmap-16": {
        "latex_ref": "04-bayesian.tex:933-987",
        "impl_file": "",
        "test_file": "",
        "status": "⚠️",
        "notes": "T3 elective, independent release decision",
    },
    "ch03-04": {
        "latex_ref": "03-model-free.tex:264-267",
        "impl_file": "",
        "test_file": "",
        "status": "⚠️",
        "notes": "Low priority wrap, listed in product register but not scheduled",
    },
    "ch04-06": {
        "latex_ref": "04-bayesian.tex:867-932",
        "impl_file": "",
        "test_file": "",
        "status": "❌",
        "notes": "T2.1 missing (10 days); V04-T1 likely failed due to missing TuRBO",
    },
    "ch05-05": {
        "latex_ref": "05-multifidelity.tex:504-506; 15-contracts.tex:140-144",
        "impl_file": "",
        "test_file": "",
        "status": "⚠️",
        "notes": "ASHA flag, 0.5 days effort",
    },
    "ch06-02": {
        "latex_ref": "06-population.tex:245-356",
        "impl_file": "",
        "test_file": "",
        "status": "⚠️",
        "notes": "T2.2-T2.3 not yet implemented (5+5 days)",
    },
    "ch07-04": {
        "latex_ref": "07-multiobjective.tex:527-568",
        "impl_file": "hponas/searchers_mo.py:461-834",
        "test_file": "tests/test_nsgaii.py:15-178",
        "status": "✓",
    },
    "ch08-01": {
        "latex_ref": "08-priors-transfer.tex:14-41,368-380",
        "impl_file": "hponas/priors.py:89-199; hponas/searchers_gp.py:351-466",
        "test_file": "tests/test_prior_recovery_pibo.py:18-134",
        "status": "✓",
        "notes": "πBO correctly implemented via PriorWeightedAcquisition wrapper (log-space additive form)",
    },
    "ch08-02": {
        "latex_ref": "08-priors-transfer.tex:76-91,381-384",
        "impl_file": "hponas/searchers_priorband.py:1-198",
        "test_file": "tests/test_priors.py:81-167",
        "status": "✓",
        "notes": "Portfolio sampler correct (verdict was stale)",
    },
    "ch08-03": {
        "latex_ref": "08-priors-transfer.tex:93-142,385-390",
        "impl_file": "hponas/warm_start.py:180-303",
        "test_file": "tests/test_warm_start.py:15-189",
        "status": "✓",
        "notes": "Ranked query correct; RGPE second wave (not in scope)",
    },
    "ch08-04": {
        "latex_ref": "08-priors-transfer.tex:93-142",
        "impl_file": "",
        "test_file": "",
        "status": "🔀",
        "notes": "Second wave, pre-gated (not Tier 1 scope)",
    },
    "ch08-05": {
        "latex_ref": "08-priors-transfer.tex:391-395",
        "impl_file": "",
        "test_file": "",
        "status": "⚠️",
        "notes": "Adopt pretrained surrogate (PFN family), train none; T3 gated",
    },
    "ch08-06": {
        "latex_ref": "08-priors-transfer.tex:396-403",
        "impl_file": "hponas/searchers_cost.py:1-356",
        "test_file": "tests/test_cost_aware.py:18-145; tests/test_cost_model_accuracy.py:18-123",
        "status": "✓",
    },
    "ch09-01": {
        "latex_ref": "09-workloads.tex:89-130; 14-product.tex:86-98",
        "impl_file": "STUB (NotImplementedError)",
        "test_file": "validation/v14_day_one_walk.py",
        "status": "⚠️",
        "notes": "T0 remediation: 5 days to build real rl_routine",
    },
    "ch09-02": {
        "latex_ref": "09-workloads.tex:189-233; 14-product.tex:86-98",
        "impl_file": "STUB (NotImplementedError)",
        "test_file": "",
        "status": "⚠️",
        "notes": "BG-PBT home regime workload, T2 scope",
    },
    "ch09-03": {
        "latex_ref": "09-workloads.tex:131-188; 14-product.tex:86-98",
        "impl_file": "examples/sampler_neutra_example.py",
        "test_file": "validation/v13_* (campaign-level test)",
        "status": "⚠️",
        "notes": "Example exists, V13 acceptance test T2",
    },
    "ch09-04": {
        "latex_ref": "09-workloads.tex:189-233; 14-product.tex:86-98",
        "impl_file": "examples/hamiltonian_mo_example.py",
        "test_file": "tests/test_hamiltonian_mo.py:15-134",
        "status": "✓",
    },
    "ch09-05": {
        "latex_ref": "11-architecture.tex:96-187; 15-contracts.tex:206-243",
        "impl_file": "hponas/architecture.py:1-158 (stubs from R1)",
        "test_file": "tests/test_architecture.py:15-134",
        "status": "⚠️",
        "notes": "Stubs; full NAS scope decision Week 1 Day 7",
    },
}


def rebuild_register(input_path: Path, output_path: Path) -> None:
    """Extend product register with traceability fields."""
    with open(input_path) as f:
        register = json.load(f)

    extended_entries = []
    for entry in register["entries"]:
        entry_id = entry["id"]

        # Add traceability fields if mapping exists
        if entry_id in TRACEABILITY:
            trace = TRACEABILITY[entry_id]
            entry["latex_ref"] = trace.get("latex_ref", "")
            entry["impl_file"] = trace.get("impl_file", "")
            entry["test_file"] = trace.get("test_file", "")
            entry["status"] = trace.get("status", "⚠️")
            if "notes" in trace:
                entry["notes"] = trace.get("notes", "")
        else:
            # Mark unmapped entries
            entry["latex_ref"] = ""
            entry["impl_file"] = ""
            entry["test_file"] = ""
            entry["status"] = "⚠️"
            entry["notes"] = "Not yet mapped in TRACEABILITY_MATRIX_v1.md"

        extended_entries.append(entry)

    # Write extended register
    register["entries"] = extended_entries
    with open(output_path, "w") as f:
        json.dump(register, f, indent=2, ensure_ascii=False)

    print(f"✓ Rebuilt product register with traceability fields")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output_path}")
    print(f"  Total entries: {len(extended_entries)}")
    mapped = sum(1 for e in extended_entries if e["status"] != "⚠️" or "Not yet mapped" not in e.get("notes", ""))
    print(f"  Mapped: {mapped}/{len(extended_entries)}")


if __name__ == "__main__":
    input_file = Path("product_register.json")
    output_file = Path("product_register_v2.json")
    rebuild_register(input_file, output_file)
