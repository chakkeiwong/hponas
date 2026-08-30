# NAS Scope Decision: Analysis and Recommendation
**Date:** 2026-08-28  
**Decision required by:** Project sponsor  
**Analysis by:** Implementation team

---

## Executive recommendation

**Adopt Option A: HPO with moderate architecture coordinates (width/depth/flags only)**

This matches the survey's explicit scope, serves the stated users, and is deliverable within a corrected timeline. General large-scale NAS (Option B) would require a separate 6-12 month survey/scoping effort and is explicitly excluded from the current governing document.

---

## Evidence from governing survey

### What the survey explicitly supports (09-workloads.tex:262-270)

> "For us, the conclusion is comfortable: architecture search should mean width, depth, and a few structural flags included as ordinal and categorical axes in the ordinary search space (as BG-PBT does for policy and value networks, with the ordinal-aware kernels of Section 5.4 doing the modeling), multi-fidelity doing the heavy lifting, parameter count reported as an objective when size matters, and no dedicated weight-sharing subsystem. That covers every architecture question our current projects actually ask, at a small fraction of the complexity."

### What the survey explicitly excludes (12-roadmap.tex:151-160)

> "Differentiable NAS and a bespoke zero-cost-proxy subsystem (Chapter 9); gradient-based HPO through the training loop; a meta-learned transformer surrogate trained by us (we adopt pre-trained ones where they ship)"

Specific exclusions from 09-workloads.tex:234-270:
- DARTS-style one-shot differentiable NAS
- Zero-cost proxy subsystem (e.g., NWOT, synflow, GraSP)
- Grammar-based topology search spaces
- Weight-sharing supernets
- Cell-based macro/micro search

### Rationale provided by survey

1. **Zero-cost proxies degrade on larger spaces** (white2023nas1000, krishnakumar2022nasbenchsuite)
2. **DARTS produces degenerate architectures** without careful regularization (zela2020robustifying)
3. **Training tricks matter more than search** in controlled evaluations (yang2020frustratingly)
4. **Good hyperparameters > architecture** in many cases (bansal2022jahs)
5. **Simple quantities (parameter count, FLOPs) competitive** with leading proxies

---

## Option A: Moderate architecture coordinates (RECOMMENDED)

### Scope

**Included:**
- Width axes (hidden dimensions, layer sizes) as ordinal parameters
- Depth axes (number of layers, residual blocks) as ordinal parameters
- Structural flags (use_attention, activation_type, normalization_type) as categorical parameters
- Parameter count and FLOPs as measured objectives (not zero-cost proxies)
- Architecture changes via BG-PBT population explore step

**Excluded:**
- Topology search (graph/cell structures, arbitrary DAGs)
- One-shot NAS (weight sharing across architectures)
- Zero-cost proxies as a subsystem
- Grammar-based search spaces
- Differentiable architecture search

### What this enables

**For RL projects (BG-PBT use case):**
- Policy network: widths [64, 128, 256], depths [2, 3, 4], activation [relu, tanh, elu]
- Value network: similar coordinate search
- Architecture changes during population evolution with distillation

**For Hamiltonian network tuning:**
- Hidden dimensions, layer counts, integrator steps as search dimensions
- Parameter count as objective alongside prediction error and energy drift

**For sampler tuning:**
- Step size schedules, momentum parameters, number of leapfrog steps
- (Architecture search less relevant here, but width/depth if neural proposals used)

### What needs to be added to current BUILD_PROGRAM

1. **Architecture factory contract** (15-contracts.tex, ~1 page)
   - Typed axis definitions (width: ordinal, depth: ordinal, flags: categorical)
   - Validity constraints (e.g., depth ≥ 2, width must be even for certain layers)
   - Deterministic model construction from configuration dict

2. **Compatibility and distillation** (BG-PBT implementation, ~6 engineer-days)
   - When can checkpoint transfer directly? (same architecture)
   - When is distillation needed? (different widths/depths)
   - Teacher selection policy (best in generation, or parent)
   - Distillation loss and schedule
   - Rollback on failed transfer

3. **Measured objectives** (executor contracts, ~2 engineer-days)
   - Parameter count (from model.parameters())
   - FLOPs (via profiler or architecture-specific calculator)
   - Peak memory, inference latency if needed

4. **Validation extensions** (V08 adjustments, minimal)
   - BG-PBT tested with architecture coordinates active
   - Baselines include random architecture + ASHA (not just random hyperparameters)

### Effort impact

**Additional to current plan:**
- Architecture contracts and factory: ~3 engineer-days (R1/early T0)
- Distillation implementation: ~6 engineer-days (T2, within BG-PBT work)
- Compatibility policy and tests: ~3 engineer-days (T2)
- Measured objectives: ~2 engineer-days (T0, part of executor contracts)
- Documentation and examples: ~2 engineer-days

**Total addition: ~16 engineer-days (~3 weeks), absorbed into T0/T2**

### Risk assessment

**Low risk:**
- Matches survey evidence and rationale
- Extends existing search-space machinery (ordinal/categorical already planned)
- No new research or unproven methods
- Distillation is standard practice (hinton2015distilling)

**Success criteria met:**
- Serves RL projects (BG-PBT's stated use case)
- Serves Hamiltonian/sampler projects (continuous HPO + modest architecture)
- Deliverable in corrected timeline
- Does not overpromise on "general NAS"

---

## Option B: General large-scale NAS (NOT RECOMMENDED)

### What this would require

**Scope additions:**
- Topology search spaces (hierarchical, graph-based, or grammar-driven)
- Cell-based macro/micro search
- One-shot NAS methods (DARTS, ENAS, etc.) with weight sharing
- Zero-cost proxy subsystem (NWOT, synflow, GraSP, etc.)
- Architecture validity checking for arbitrary graphs
- Extensive NAS benchmarks (NAS-Bench-201, NATS-Bench, etc.)

**Survey work required:**
- 50-100 page chapter on NAS methods landscape
- Evidence review of topology search, one-shot methods, zero-cost proxies
- Benchmark protocol for NAS (training from scratch, weight-sharing bias, etc.)
- Decision boxes for: topology encoding, validity constraints, weight-sharing policy, zero-cost proxy selection, transfer protocol

**Implementation impact:**
- Architecture representation: 10-15 engineer-weeks (graph ADT, validity checking, encoding)
- One-shot search: 8-12 engineer-weeks (supernet training, weight sharing, architecture sampling)
- Zero-cost proxies: 6-10 engineer-weeks (10+ proxy implementations, benchmarking, integration)
- Validation: 8-12 GPU-weeks (NAS-specific benchmarks, training-from-scratch validation)

**Total effort addition: 50-80 engineer-weeks (10-16 months at 1 engineer, 5-8 months at 2)**

### Why NOT recommended

1. **Survey explicitly excludes it** — changing scope requires new governing document
2. **Evidence does not support ROI** — survey's literature review concludes simple methods sufficient
3. **No current project needs it** — stated users (RL, Hamiltonian, samplers) served by Option A
4. **Timeline impact unacceptable** — adds 10-16 months to already-corrected 38-46 week plan
5. **Risk substantially higher** — DARTS degeneracy, proxy reliability, weight-sharing bias are open research problems

---

## Comparison table

| Dimension | Option A (Moderate) | Option B (General) |
|-----------|-------------------|-------------------|
| **Scope match** | Exact match to survey | Contradicts survey exclusions |
| **User needs** | Serves all stated projects | No current user requires it |
| **Evidence base** | Strong (survey Ch. 9) | Survey explicitly argues against |
| **Timeline** | +3 weeks to corrected plan | +10-16 months |
| **Effort** | +16 engineer-days | +50-80 engineer-weeks |
| **Risk** | Low (extends existing) | High (open research) |
| **Validation** | Minimal additions to V08 | New 8-12 GPU-week suite |
| **Deliverable** | Yes, in corrected timeline | No, requires new program |

---

## Recommended decision

**Adopt Option A: HPO with moderate architecture coordinates**

### Immediate actions if approved

1. Add architecture scope subsection to survey 09-workloads.tex (document boundary)
2. Add architecture factory contract to 15-contracts.tex
3. Add distillation protocol to BG-PBT implementation plan (T2)
4. Update BUILD_PROGRAM_v2 with +16 engineer-days in T0/T2
5. Clarify marketing: "joint hyperparameter and architecture optimization for width/depth/flags," NOT "general NAS product"

### What to say when asked about broader NAS

"The product supports joint hyperparameter and architecture optimization over width, depth, and structural flags—the architecture questions our RL and Hamiltonian network projects actually ask. We deliberately exclude topology search, one-shot methods, and zero-cost proxy subsystems based on the survey's evidence review. If a future project needs broader NAS, we would scope that separately with its own survey and validation strategy."

---

## Decision record

**Date:** 2026-08-28  
**Decision maker:** Project sponsor  
**Decision:** [X] Option A (moderate architecture coordinates)  
**Decision:** [ ] Option B (general NAS, requires new governing document)  
**Decision:** [ ] Out of scope entirely (pure HPO, no architecture search)

**Approved:** 2026-08-28  
**Status:** Implemented — scope boundary written into survey Ch 9, architecture factory contract in Ch 15, +16 engineer-days in work breakdown

---

## Next steps after decision

**If Option A approved:**
- Task 1.6: Add architecture scope to survey (2 days)
- Task 1.7: Add architecture contracts to 15-contracts.tex (3 days)
- Update R1 spike to include architecture factory prototype
- Update work breakdown with +16 engineer-days

**If Option B selected:**
- STOP current program
- Initiate NAS survey scoping (6-12 months)
- Reassess staffing and budget for 10-16 month addition

**If out of scope:**
- Remove BG-PBT architecture components from plan
- Simplify to fixed-architecture population-based training
- Reduce T2 scope and timeline accordingly
