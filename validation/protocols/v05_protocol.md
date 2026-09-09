# V05 Protocol: Real Workload Performance

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 0  

---

## Claim

Methods work on real RL task with actual Brax/JAX evaluation, not just synthetic proxies.

**Operational requirement:** Proxy objectives (V04) establish relative performance, but production deployment requires validation on real workload.

---

## Hypothesis

### H0 (Null Hypothesis)
Random search does not improve over pathological baseline on real rl_routine with Brax/JAX evaluation.

### H1 (Alternative Hypothesis)
Random search improves over pathological baseline by at least δ = 0.05 (5% margin) on real evaluation.

### Test Type
**Superiority test** (one-sided) - random must beat pathological on real workload.

---

## Preregistration

### Task
**Benchmark:** rl_routine with real Brax/JAX evaluation
- Environment: Brax Ant-v0 or HalfCheetah-v0
- Evaluation: Full episode return (not proxy)
- Training: 100K environment steps per trial
- Estimated time: 5-10 minutes per trial on GPU

**Search space (simplified for Tier 0 cost):**
- learning_rate ∈ [1e-5, 1e-2] (log scale)
- batch_size ∈ [64, 512] (ordinal)
- entropy_cost ∈ [0.0, 0.1] (continuous)

**Pathological baseline:** Same as V04-T0
- learning_rate = 1e-5 (too low)
- batch_size = 64 (too small)
- entropy_cost = 0.1 (too high)

### Seeds
**Preregistered seeds:** 0, 1, 2 (3 seeds only due to GPU cost)

**Rationale:** Each trial takes 5-10 min on GPU. 3 seeds × 50 trials = 150 trials ≈ 12-25 GPU-hours.

### Margin
**Superiority margin:** δ = 0.05 (5% improvement required)

**Justification:** Same as V04-T0, but on real workload validates proxy was representative.

### Alpha
α = 0.05 (one-sided test)

**Family correction:** Per protocols.json lines 19-26, V05 is in tier0_gate family with V04-T0 (m=2).
- Holm-Bonferroni corrected α: depends on ordering
- If V05 tests second: α₂ = 0.05/1 = 0.05 (no correction after first rejected)
- Conservative: use α = 0.05 (assume first test didn't reject)

### Power
- Target: 0.80
- Method: Simulation under task hierarchy
- Pilot: Use V04-T0 proxy results to estimate variance order-of-magnitude

**Challenge:** Real workload has higher variance than proxy. May need to increase n_trials or accept lower power.

### Sample Size
**Preregistered:**
- n_trials = 50 per seed
- n_seeds = 3
- Total GPU-hours: ~12-25 hours

**Max sample:** n_trials = 100 (computational budget limit)

### Analysis

**Primary endpoint:** Area under incumbent curve (AUC) - measures convergence speed.

**Statistical test:** Mann-Whitney U test (one-sided)
- Compare random_auc vs pathological_auc
- Alternative: 'greater' (random > pathological)

**Pass criteria:**
- Improvement = (mean(random_auc) - mean(pathological_auc)) / mean(pathological_auc)
- Improvement ≥ 0.05 (5% margin)
- p-value < 0.05

---

## Decision States

### PASS
**All of the following must be true:**
1. Improvement ≥ 5%
2. p < 0.05
3. Real Brax/JAX evaluation used (not proxy)
4. V16 audit: non-vacuous, threshold preregistered

### FAIL
**Any of the following:**
1. Improvement < 5%
2. p ≥ 0.05
3. V16 audit fails

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.80 at max_sample (n_trials=100)
2. Brax/JAX dependency not available
3. GPU not available

**Resolution:** If INCONCLUSIVE due to dependencies, document as blocker for Tier 0 gate.

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v05_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v05_results.json
- **Format:** JSON with structure:
  ```json
  {
    "validation_id": "v05",
    "timestamp": "ISO8601",
    "random_auc_mean": float,
    "pathological_auc_mean": float,
    "improvement": float,
    "p_value": float,
    "passed": bool,
    "n_trials": 50,
    "n_seeds": 3,
    "margin": 0.05,
    "brax_environment": "Ant-v0",
    "training_steps": 100000,
    "gpu_hours": float,
    "v16_audit": {"passed": bool, "checks": [...]}
  }
  ```
- **Write policy:** Write once, never modified

### Log
- **Path:** validation/results/v05_log.txt
- **Format:** Append-only text log

---

## Implementation

### Scripts
- **Main:** validation/v05_real_workload.py (to be created, replace v05_log_warping.py)
- **Validator:** validation/validators/v05_validator.py (V16-compliant)

### Execution
```python
# Real Brax/JAX evaluation
def rl_routine_real(config: dict) -> float:
    """Train PPO agent with Brax/JAX."""
    import jax
    import brax
    from brax.training import ppo
    
    # Configure PPO
    env = brax.envs.create("ant")
    train_fn = ppo.train(
        environment=env,
        learning_rate=config["learning_rate"],
        batch_size=config["batch_size"],
        entropy_cost=config["entropy_cost"],
        num_timesteps=100_000
    )
    
    # Train and evaluate
    _, eval_metrics = train_fn(rng=jax.random.PRNGKey(42))
    return eval_metrics["episode_return"]

# Run validation
random_auc = run_optimization(RandomSearcher, space, rl_routine_real, n_trials=50, seeds=[0,1,2])
pathological_auc = run_pathological(pathological_config, rl_routine_real, n_trials=50, seeds=[0,1,2])
```

### Dependencies
- **Required:**
  - jax>=0.4.0
  - brax>=0.9.0 (Brax RL library)
  - GPU with CUDA support

**Blocker:** If dependencies unavailable, V05 cannot run, Tier 0 gate blocked.

---

## Known Issues

### Issue 1: Currently Implements Log-Warping
**Problem:** validation/v05_log_warping.py implements log-warping effectiveness test, not real workload.

**Resolution:** Master program describes V05 as real workload validation. Log-warping is covered by space.py Knob transform tests.

**Action:** Replace v05_log_warping.py with v05_real_workload.py implementing this protocol.

**Status:** To be implemented during Week 3 Day 1-3.

### Issue 2: GPU Cost
**Problem:** 150 trials × 5-10 min = 12-25 GPU-hours is expensive for gate validation.

**Resolution:** 
- Reduced seeds (3 vs 5 in V04-T0)
- Alternative: Use cheaper environment (CartPole) for gate, full Ant for acceptance
- Max sample limit (n_trials=100) prevents runaway cost

**Status:** Accepted cost for real workload validation.

### Issue 3: Brax/JAX Dependency
**Problem:** Brax not in current dependencies.

**Resolution:** Week 1 Day 7 identifies jax/brax as 0.5-day dependency installation task.

**Blocker:** V05 blocks Tier 0 gate if dependency missing.

### Issue 4: Variance Higher Than Proxy
**Problem:** Real RL training has high variance (exploration, initialization, environment stochasticity).

**Resolution:**
- V04-T0 proxy provides variance lower bound
- If n_seeds=3 insufficient, escalation to n_seeds=5 allowed
- Max sample rule: if variance too high for power, verdict='inconclusive'

**Status:** Power analysis determines if 3 seeds sufficient.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_trials > 0, n_seeds > 0
- [ ] Real Brax/JAX used (not proxy objective)
- [ ] Training actually runs (not mocked)

### Check 2: No Post-Hoc Tuning
- [ ] Margin (5%) preregistered in protocol
- [ ] Pathological config preregistered (same as V04-T0)
- [ ] Seeds preregistered

### Check 3: Correct Reference
- [ ] Compares to pathological baseline, not to self
- [ ] Baseline is genuinely bad config (justified)

### Check 4: Runnable Independently
- [ ] Script runs without manual intervention (given GPU/dependencies)
- [ ] Results written atomically
- [ ] Logs capture training progress

---

## References

**Authority:**
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 754-760 (V05 repair)
- protocols.json lines 19-26 (tier0_gate family)

**Related Protocols:**
- V04-T0 (random baseline floor on proxy)
- V04-T1 (Sobol vs random on proxy)

**Dependency:**
- Week 1 Day 7: jax/brax installation (0.5 days)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial preregistered protocol
- Real Brax/JAX evaluation (not proxy)
- Margin: 5% (consistent with V04-T0)
- Sample size: n_trials=50, n_seeds=3 (GPU cost reduction)
- Environment: Brax Ant-v0, 100K training steps
- Max sample: n_trials=100 (budget limit)
- Documented replacement of v05_log_warping.py

---

**END OF PROTOCOL**
