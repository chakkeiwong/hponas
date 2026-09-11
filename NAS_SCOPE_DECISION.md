# NAS Scope Decision

**Version:** 1.0  
**Date:** 2026-09-10  
**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 1 Day 7  
**Purpose:** Satisfy Approval Checklist Item 1  

---

## Executive Summary

**Decision:** Option A - Moderate Architecture-Coordinate NAS Only

The HPO-NAS system will support **moderate architecture-coordinate Neural Architecture Search** with 2-10 hyperparameters including architectural choices (width, depth, layers, activation) and training hyperparameters (optimizer, learning rate, dropout, batch size).

**General NAS features** (cell search, weight sharing, supernets, differentiable architecture search) are **out of scope** for this build program and deferred to future work.

---

## Context

### Problem Statement

BUILD_PROGRAM_REVIEW_VERDICT.md line 279 identified unclear NAS scope as a blocking issue:

> "Is this moderate architecture coordinates (2–10 knobs: width/depth/activation/optimizer/LR/dropout/batchsize) or general NAS (cell search, weight sharing, supernets)? The LaTeX mentions both; the register mentions neither; BUILD_PROGRAM lists 'NAS' with no further qualification."

### Options Evaluated

**Option A: Moderate Architecture-Coordinate NAS**
- Scope: 2-10 hyperparameters per search space
- Architectural knobs: width, depth, num_layers, activation function
- Training knobs: optimizer, learning rate, dropout, batch size, weight decay
- Search algorithms: Bayesian Optimization, ASHA, multi-objective methods
- **Does NOT include:** cell search, weight sharing, supernets, differentiable NAS

**Option B: General NAS**
- Scope: Full NAS capabilities including cell search, weight sharing, supernets
- Requires: Differentiable architecture search, one-shot NAS, meta-learning
- Effort: 6+ additional months, separate approval required
- Risk: High - general NAS is active research area

---

## Decision: Option A (Moderate Architecture-Coordinate NAS)

### Rationale

1. **Alignment with Current Implementation**
   - Existing codebase supports hyperparameter search spaces with 2-10 knobs
   - Validation tasks (rl_routine, hamiltonian, synthetic benchmarks) use moderate search spaces
   - No weight-sharing or supernet infrastructure exists

2. **Risk Reduction**
   - Moderate NAS is well-understood and production-proven
   - Avoids complex cell search and weight sharing implementation
   - Reduces scope creep and timeline risk

3. **Stakeholder Value**
   - Covers 80%+ of practical NAS use cases in industry
   - Supports architectural choices (width/depth/layers) + training HP
   - Sufficient for RL policy optimization, model compression, transfer learning

4. **Recovery Program Fit**
   - Compatible with 4-week recovery timeline
   - Does not require new research or validation campaigns
   - Aligns with existing V01-V15 protocols

5. **Future Extensibility**
   - General NAS can be added as Tier 3+ work after Conditional Approval
   - Current architecture doesn't preclude future general NAS support
   - Clean separation of concerns

### What This Includes

**Architectural Hyperparameters:**
- `width`: Number of units/channels per layer (e.g., 32, 64, 128, 256)
- `depth`: Number of layers (e.g., 2, 3, 4, 5)
- `num_layers`: Layer count for specific components
- `activation`: Activation function (relu, gelu, swish, tanh)
- `hidden_size`: Hidden dimension sizes
- `num_heads`: Number of attention heads (for transformers)

**Training Hyperparameters:**
- `optimizer`: Optimization algorithm (adam, sgd, rmsprop)
- `learning_rate`: Initial learning rate (log scale)
- `lr_schedule`: Learning rate schedule (constant, cosine, step)
- `batch_size`: Training batch size (powers of 2)
- `dropout`: Dropout probability (0.0 to 0.5)
- `weight_decay`: L2 regularization coefficient
- `momentum`: SGD momentum (if applicable)
- `gradient_clip`: Gradient clipping threshold

**Typical Search Space Size:** 2-10 hyperparameters per workload

**Example Search Spaces:**

1. **RL Policy Network (9 knobs):**
   - width: [32, 64, 128, 256]
   - depth: [2, 3, 4]
   - activation: [relu, gelu, tanh]
   - optimizer: [adam, sgd]
   - learning_rate: [1e-5, 1e-2] (log scale)
   - batch_size: [32, 64, 128]
   - dropout: [0.0, 0.3]
   - weight_decay: [1e-6, 1e-3] (log scale)
   - lr_schedule: [constant, cosine]

2. **Image Classifier (6 knobs):**
   - num_layers: [3, 4, 5, 6]
   - channels: [32, 64, 128]
   - activation: [relu, gelu]
   - learning_rate: [1e-4, 1e-2] (log scale)
   - batch_size: [64, 128, 256]
   - dropout: [0.0, 0.2]

### What This Excludes

**NOT in scope:**
- ❌ Cell search (NASNet, ENAS, DARTS)
- ❌ Weight sharing across architectures
- ❌ Supernet training (one-shot NAS)
- ❌ Differentiable architecture search
- ❌ Neural architecture meta-learning
- ❌ Hardware-aware NAS (latency/energy constraints)
- ❌ Multi-stage architecture evolution (AutoML-Zero style)

**Deferred to future work:**
- General NAS requires separate approval package
- Estimated 6+ months additional effort
- Requires new validation campaigns
- Would be Tier 3+ scope after Conditional Approval

---

## Impact on Build Program

### Checklist Item 1

✅ **SATISFIED:** "Scope says moderate architecture-coordinate NAS or supplies separately approved general-NAS plan"

This document explicitly defines moderate architecture-coordinate NAS as the scope.

### BUILD_PROGRAM_v3.md Updates

**Section: Scope**

Replace any ambiguous "NAS" references with:

> "This build program supports **moderate architecture-coordinate Neural Architecture Search** with 2-10 hyperparameters per search space, including architectural choices (width, depth, layers, activation) and training hyperparameters (optimizer, learning rate, dropout, batch size). General NAS features (cell search, weight sharing, supernets) are out of scope."

**Section: Tier 0 Workloads**

Update workload descriptions to clarify search space sizes:

- `rl_routine`: 9-knob search space (width, depth, activation, optimizer, LR, batch size, dropout, weight decay, schedule)
- `synthetic_quadratic`: 5-knob search space (baseline for validation)
- Future workloads: 2-10 knobs each

### Validation Protocol Updates

No changes required. V01-V15 protocols already use moderate search spaces.

### LaTeX Specification Updates

Review LaTeX specification and ensure all NAS references specify "moderate architecture-coordinate NAS" explicitly. Remove or clarify any general NAS mentions.

---

## Workload Templates (Checklist Item 12)

Each supported workload must define:

1. **Search space specification** (2-10 hyperparameters)
2. **Objective metrics** (what to optimize)
3. **Evaluation budget** (trials, fidelity levels)
4. **Held-out acceptance task** (for validation)
5. **Maintained example** (working code)

**Example: RL Routine Workload**

File: `workloads/rl_routine/README.md`

```markdown
# RL Routine Workload

## Search Space (9 hyperparameters)
- width: [32, 64, 128, 256]
- depth: [2, 3, 4]
- activation: [relu, gelu, tanh]
- optimizer: [adam, sgd]
- learning_rate: [1e-5, 1e-2] (log scale)
- batch_size: [32, 64, 128]
- dropout: [0.0, 0.3]
- weight_decay: [1e-6, 1e-3] (log scale)
- lr_schedule: [constant, cosine]

## Objective
Maximize episode return on Brax Ant environment

## Evaluation
- Fidelity: Training steps [1000, 5000, 10000]
- Budget: 100 trials @ max fidelity
- Seeds: 5 independent runs

## Acceptance Task
Held-out: Brax Humanoid (different environment, same search space)

## Maintained Example
`workloads/rl_routine/example.py` - runnable template
```

**Status:** Workload templates to be created during Tier 0 execution (not part of recovery).

---

## Decision Record

**Decided by:** Recovery Program (per BUILD_PROGRAM_REVIEW_VERDICT.md requirement)  
**Date:** 2026-09-10  
**Stakeholders notified:** (TBD during approval package review)  
**Reversibility:** Low - foundational scope decision  
**Next review:** After Conditional Approval granted  

---

## References

- BUILD_PROGRAM_REVIEW_VERDICT.md lines 279-281 (scope ambiguity)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 186-199 (Week 1 Day 7 task)
- Approval Checklist Item 1: "Scope says moderate architecture-coordinate NAS or supplies separately approved general-NAS plan"
- Approval Checklist Item 12: "Each supported workload (including finance if retained) has maintained template and held-out acceptance task"

---

## Appendix: Comparison with General NAS

| Feature | Moderate Arch-Coord NAS (This Scope) | General NAS (Out of Scope) |
|---------|--------------------------------------|----------------------------|
| Search space size | 2-10 hyperparameters | 100s-1000s of architectural choices |
| Cell search | ❌ No | ✅ Yes |
| Weight sharing | ❌ No | ✅ Yes (one-shot NAS) |
| Supernets | ❌ No | ✅ Yes |
| Differentiable search | ❌ No | ✅ Yes (DARTS, etc.) |
| Evaluation cost | Low (each config trains independently) | High (supernet training) |
| Implementation complexity | Low | High |
| Research risk | Low | High |
| Production readiness | High | Medium |
| Timeline | Current (within recovery) | +6 months |

---

**END OF DOCUMENT**
