# NAS Scope Decision v1.0

**Date:** 2026-09-04  
**Authority:** BUILD_PROGRAM_REVIEW_VERDICT.md approval checklist item 1  
**Requirement:** "Scope says moderate architecture-coordinate NAS or supplies separately approved general-NAS plan"  
**Status:** ✅ MODERATE ARCHITECTURE COORDINATES (Option A affirmed)

---

## Executive Summary

**Decision:** Affirm **Option A (moderate architecture coordinates)** as documented in BUILD_PROGRAM_v2.md line 43 and specified in hpo-survey sections 9 and 15.

**Rationale:** Option A already approved 2026-08-28 during R0 completion. This document provides the explicit scope boundary required by the approval checklist, confirms the decision remains correct after traceability analysis, and documents the excluded general NAS approaches.

**Impact:** Retain Tier 2 architecture tasks T2.5-T2.9 and T2.12 (20 eng-days total, NAS specialist required weeks 17-20).

---

## Scope Boundary

### IN SCOPE: Moderate Architecture Coordinates

**Definition (from 09-workloads.tex:189-233):**

Architecture search means **width, depth, and a few structural flags** included as ordinal and categorical axes in the ordinary search space, with:

1. **Width and depth as ordinal axes** (e.g., `hidden_dim ∈ [64, 128, 256, 512]`, `num_layers ∈ [2, 3, 4, 5, 6]`)
2. **Structural flags as categorical axes** (e.g., `norm_type ∈ [batch, layer, none]`, `activation ∈ [relu, gelu, swish]`, `use_residual ∈ [True, False]`)
3. **Parameter count and FLOPs as measured objectives** (not proxies) for multi-objective optimization (Chapter 7)
4. **Distillation protocol for incompatible parent→child transfers** (BG-PBT population methods, Tier 2)

**Key property:** No dedicated weight-sharing subsystem, no supernet, no cell-based topology search.

### OUT OF SCOPE: General NAS

**Explicitly excluded approaches (from 09-workloads.tex:283-351, 12-roadmap.tex:46):**

1. **One-shot / differentiable NAS** (DARTS, ENAS, supernet-based methods)
   - **Why excluded:** Documented degenerate solutions, reliability evidence poor
   - **Verdict:** Skip (12-roadmap.tex:46)

2. **Cell-based search** (NASNet, AmoebaNet search spaces)
   - **Why excluded:** Requires topology grammar, outside "moderate" boundary
   - **Complexity:** Would require graph representation, architecture grammar, separate approval

3. **Hierarchical search spaces** (cell → macro structure)
   - **Why excluded:** Exceeds ordinal/categorical modeling capability
   - **Would require:** Multi-level search space abstraction, not in current contracts

4. **Zero-cost proxy subsystems** (synflow, NWOT, grad-based scoring)
   - **Why excluded:** Chapter 9 verdict "unwilling to treat proxies as substitute for training"
   - **Our approach:** Measure actual parameter count and FLOPs, train with multi-fidelity

---

## Architecture Factory Contract

**Source:** 15-contracts.tex:214-260 (sec:archfactory)

The moderate scope is enforced by contract design:

```python
class ArchitectureFactory(Protocol):
    def build(self, config: Dict) -> nn.Module:
        """Map architecture coordinates to initialized model."""
        pass
    
    def measure(self, model: nn.Module) -> Tuple[int, int]:
        """Return (param_count, flops_per_forward)."""
        pass
    
    def compatible(self, config_a: Dict, config_b: Dict) -> bool:
        """True if weights from config_a can load into config_b."""
        pass
    
    def transfer(self, parent_ckpt, child_config) -> nn.Module:
        """Policy for incompatible inheritance: restart or distill."""
        pass
```

**Key constraint:** A contract that maps coordinates to a model has no place to put a supernet (15-contracts.tex:233-234). The contract design makes excluded methods **excluded by construction**.

---

## Tier 2 Architecture Tasks

**From WORK_BREAKDOWN_v3.csv lines 64-68, 71:**

| Task ID | Task Name | Effort | Staff | Week |
|---------|-----------|--------|-------|------|
| T2.5 | Architecture Factory Contract | 3 days | NAS specialist | 17-18 |
| T2.6 | Compatibility Policy | 2 days | NAS specialist | 18 |
| T2.7 | Distillation Protocol | 5 days | NAS specialist | 18-19 |
| T2.8 | Architecture Proposal Method | 4 days | NAS specialist | 19-20 |
| T2.9 | Measured Objectives (params/FLOPs/latency) | 3 days | NAS specialist | 20 |
| T2.12 | Distillation Correctness Tests | 3 days | NAS specialist | 19-20 |
| **Total** | | **20 days** | | |

**Dependencies:**
- All architecture tasks depend on T2.1 (Mixed-Space TuRBO) completing
- BG-PBT (T2.4) depends on distillation protocol (T2.7)
- V08 campaign depends on full architecture stack (T2.5-T2.9, T2.12)

**Staffing:** NAS specialist (TBH) required weeks 17-20, 20 eng-days total
- **Required skills:** Neural architecture search, knowledge distillation, PyTorch internals
- **Fallback:** Remove architecture NAS scope if hire fails, reduce T2 by 20 days, update scope documents

---

## Workload Coverage

**Architecture-aware workloads (from WORK_BREAKDOWN_v3.csv, TRACEABILITY_MATRIX_v1.md):**

### T2.13: rl_large_parallel
- **LaTeX ref:** 09-workloads.tex:189-233 (BG-PBT home regime)
- **Architecture coordinates:** Policy/value network width, depth, activation
- **Population method:** BG-PBT with incompatible parent→child transfers requiring distillation
- **Validation:** V08 campaign (240 GPU-hours, A100 × 16)

### T1.12: hamiltonian_mo (architecture-light)
- **LaTeX ref:** 09-workloads.tex:189-233
- **Architecture coordinates:** Network width for Hamiltonian sampler
- **Status:** ✓ Implemented (examples/hamiltonian_mo_example.py)
- **Validation:** Passed T1 tests

### T1.13: sampler_neutra (architecture-light)
- **LaTeX ref:** 09-workloads.tex:131-188
- **Architecture coordinates:** Minimal (sampler hyperparameters dominate)
- **Status:** Example exists (examples/sampler_neutra_example.py)
- **Validation:** V13 campaign (deferred to T2)

---

## Comparison to R0 Decision

**R0 completion report (BUILD_PROGRAM_v2.md:43) stated:**
> NAS scope decided (Option A: moderate architecture coordinates, +16 eng-days)

**Reconciliation with current work breakdown:**
- R0 claimed +16 eng-days for architecture support
- WORK_BREAKDOWN_v3.csv shows 20 eng-days (T2.5-T2.9, T2.12)
- **Difference:** 4 days (20% increase)
- **Cause:** R0 estimate predated distillation correctness tests (T2.12, 3 days) and detailed task decomposition
- **Resolution:** Accept 20-day estimate as refined bottom-up accounting, update BUILD_PROGRAM_v3 with correct total

---

## Decision Criteria

### Why Option A (moderate) is correct:

1. **Covers actual project needs:** All current RL workloads ask width/depth/structural questions, not cell topology
2. **Contract-compatible:** Architecture factory maps coordinates→model cleanly, no supernet required
3. **Tier 2 scope manageable:** 20 eng-days, single specialist, 4-week window
4. **Validation feasible:** V08 tests BG-PBT distillation protocol, existing infrastructure sufficient
5. **No separate approval needed:** Moderate scope was pre-authorized in survey Chapter 9 verdict

### Why Option B (general NAS) is rejected:

1. **Separate approval required:** Approval checklist item 1 explicitly calls out general NAS as needing separate approval
2. **Complexity explosion:** Would add cell grammar, supernet training, topology search (+40-60 eng-days estimate)
3. **No current project demand:** No RLlib workload asks for cell-based or hierarchical search
4. **Reliability concerns:** Survey Chapter 9 documented DARTS degenerate solutions, excluded one-shot methods
5. **Contracts incompatible:** build(config) has no place to put a supernet, would require redesign of 15-contracts.tex

---

## Approval Checklist Item 1 Satisfaction

**Requirement (BUILD_PROGRAM_REVIEW_VERDICT.md:314):**
> "Scope says moderate architecture-coordinate NAS or supplies separately approved general-NAS plan"

**Status:** ✅ SATISFIED

**Evidence:**
1. ✅ Moderate architecture coordinates explicitly defined (width, depth, structural flags)
2. ✅ Scope boundary documented with IN/OUT lists
3. ✅ Excluded methods enumerated (DARTS, supernets, cell-based, hierarchical)
4. ✅ Contract design enforces moderate scope by construction
5. ✅ Workload coverage confirmed (rl_large_parallel as anchor workload)
6. ✅ Tier 2 tasks (T2.5-T2.9, T2.12) scoped to moderate approach
7. ✅ No general NAS plan supplied (not needed, Option A affirmed)

---

## Next Steps

### Immediate (Week 1 Day 7 complete):
1. ✅ NAS_SCOPE_DECISION.md created
2. ⏭️ Update phase marker to Week 1 Day 7 complete
3. ⏭️ Git commit Week 1 Day 7 deliverable

### Week 2 (W2.1-W2.6):
- Implement contract conformance tests for Searcher, Scheduler, Executor, Store, Checkpoint (5 days)
- Define missing contract semantics (2 days)
- Architecture factory contract conformance deferred to Tier 2 (T2.5-T2.9 will implement)

### Week 4 (W4.1-W4.6):
- Update BUILD_PROGRAM_v3.md Tier 2 scope section with 20-day architecture estimate (was 16 in R0)
- Document architecture tasks T2.5-T2.9, T2.12 in Tier 2 specification
- Include NAS specialist hiring requirement in approval package

---

## References

- **LaTeX specification:** hpo-survey/sections/09-workloads.tex:189-233 (architecture scope)
- **Contract specification:** hpo-survey/sections/15-contracts.tex:214-260 (architecture factory)
- **Roadmap verdict:** hpo-survey/sections/12-roadmap.tex:46 (one-shot/zero-cost NAS excluded)
- **R0 decision:** BUILD_PROGRAM_v2.md:43 (Option A approved 2026-08-28)
- **Work breakdown:** WORK_BREAKDOWN_v3.csv lines 64-68, 71 (architecture tasks)
- **Approval requirement:** BUILD_PROGRAM_REVIEW_VERDICT.md:314 (checklist item 1)

---

**VERDICT:** Option A (moderate architecture coordinates) affirmed. Approval checklist item 1 satisfied.

**END OF DECISION DOCUMENT**
