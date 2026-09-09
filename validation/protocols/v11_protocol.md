# V11 Protocol: Prior Recovery (V11a + V11b)

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 1  

---

## Claim

**V11a:** Priors help under good advice - folklore prior beats no prior.  
**V11b:** Priors recover under wrong advice - wrong prior does not fall below no prior by >10%.

**Consequence:** Failure/inconclusive triggers demotion of πBO/PriorBand to opt-in.

---

## Hypotheses

### V11a: Folklore Prior Helps

**H0:** folklore_prior does not beat no_prior.  
**H1:** folklore_prior beats no_prior by at least δ margin.  
**Test type:** Superiority (one-sided)

### V11b: Wrong Prior Recovers

**H0:** wrong_prior falls below no_prior by >10%.  
**H1:** wrong_prior does not fall below no_prior by >10% (recovery threshold).  
**Test type:** Non-inferiority (one-sided)

---

## Preregistration

### Tasks
**Benchmark suite:** V11_ACCEPTANCE_TASKS (from v11_tasks.py)
- 4 tasks × 2 method families (πBO, PriorBand) = 8 clusters
- Tasks: synthetic functions with known optimal regions

**Arms:**
- no_prior (comparator)
- folklore_prior (domain knowledge)
- wrong_prior (adversarial prior)

### Seeds
**Pilot seeds (COMPLETED):** 5 replicates (pilot_seeds() from v11_tasks.py)  
**Confirmatory seeds (BLOCKED):** TBD, disjoint from pilot per protocols.json line 91

### Margins

**V11a (superiority):** δ = 0.05 (5% improvement)  
**V11b (non-inferiority):** δ = -0.10 (-10% degradation acceptable)

### Alpha
α = 0.05 per entry

**Family correction:** Per protocols.json lines 27-38, V11a and V11b are in tier1_gate family (m=6).
- Holm-Bonferroni: conservative α = 0.01 per entry

### Power
- **Target:** 0.80 standard, 0.90 high (V11 not listed as high-stakes)
- **Method:** Simulation under cluster hierarchy
- **Pilot variance:** Conservative UCB on variance estimate

**Pilot results (2026-09-04):**
- V11a: point=+0.0604, lb=-0.0002, p=0.0195, verdict=inconclusive
- V11b: point=-0.0249, lb=-0.1125, p=0.0172, verdict=inconclusive

**Sizing results:**
- V11a: NOT SIZED (power 0.258 at max_sample=20)
- V11b: NOT SIZED (power 0.542 at max_sample=20)

**Interpretation:** Effect sizes too small relative to variance for confirmatory to reach target power.

### Sample Size

**Pilot (COMPLETED 2026-09-04):**
- n_studies = 120 (4 tasks × 2 methods × 3 arms × 5 replicates)
- n_trials = 25 per study
- Duration: 17.9 minutes

**Confirmatory (BLOCKED):**
- Per protocols.json line 94 max_sample_rule: if max_sample reached without crossing threshold → verdict='inconclusive'
- Sizing analysis shows confirmatory would also be INCONCLUSIVE

**Status:** Pilot complete, confirmatory blocked on insufficient power.

### Analysis

**Primary endpoint:** Best objective value at trial budget (n_trials=25)

**Statistical test:** 
- V11a: Superiority test (folklore > no_prior)
- V11b: Non-inferiority test (wrong ≥ no_prior - 0.10)

**Cluster structure:** (task, method) pairs, paired study replicates

**Pass criteria:**
- V11a: improvement ≥ 5%, p < 0.01, power ≥ 0.80
- V11b: degradation ≤ 10%, p < 0.01, power ≥ 0.80

---

## Decision States

### PASS
**All of the following must be true:**
1. V11a: improvement ≥ 5%, p < 0.01, power ≥ 0.80
2. V11b: degradation ≤ 10%, p < 0.01, power ≥ 0.80
3. V16 audit: non-vacuous, threshold preregistered

### FAIL
**Any of the following:**
1. V11a: improvement < 5% OR p ≥ 0.01
2. V11b: degradation > 10% OR p ≥ 0.01

**Consequence:** Demote πBO/PriorBand to opt-in.

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.80 at max sample
2. Pilot shows effect too small to size confirmatory

**Status (2026-09-04):** V11 INCONCLUSIVE (pilot complete, confirmatory undersized)

**Consequence per protocols.json lines 96-100:** Apply demotion rule (treat INCONCLUSIVE as FAIL given opt-in release consequence).

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v11_protocol.md
- **Status:** Immutable (pilot completed)
- **Hash:** (git commit hash when frozen)

### Results

**Pilot:**
- **Path:** validation/results/v11_pilot.json
- **Summary:** validation/results/v11_pilot_summary.json
- **Sizing:** validation/results/v11_sizing.json

**Confirmatory:**
- **Status:** BLOCKED (insufficient power)

### Log
- **Path:** validation/results/v11_log.txt

---

## Implementation

### Scripts
- **Main:** validation/v11_campaign.py (existing, pilot COMPLETE)
- **Tasks:** validation/v11_tasks.py (task definitions)
- **Sizing:** validation/size_v11_confirmatory.py (power analysis)
- **Validator:** validation/validators/v11_validator.py (V16-compliant)

### Dependencies
- hponas.searchers_priorband (PriorBandSampler)
- hponas.searchers (πBO with prior_fn)
- validation.stats (paired cluster analysis)

---

## Known Issues

### Issue 1: Pilot Inconclusive
**Status:** Pilot executed 2026-09-04, both V11a and V11b INCONCLUSIVE.

**Root cause:** Effect sizes (6.04% for V11a, -2.49% for V11b) too small relative to variance.

**Resolution:** Per protocols.json max_sample_rule, verdict='inconclusive' is terminal.

### Issue 2: Confirmatory Undersized
**Status:** Sizing analysis shows confirmatory cannot reach target power at max_sample=20.

**Resolution:** Per protocols.json lines 96-100, one replication permitted with preregistered budget. Sizing shows replication would also be inconclusive.

**Decision:** Apply demotion rule (πBO/PriorBand to opt-in).

### Issue 3: Demotion Applied
**Status (2026-09-04):** Per BUILD_PROGRAM_v2.md lines 252-256, πBO/PriorBand demoted to opt-in.

**Consequence:** Methods ship but not as defaults. Users must explicitly enable.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [x] Pilot: 120 studies, 25 trials each
- [x] All arms (no_prior, folklore_prior, wrong_prior) run

### Check 2: No Post-Hoc Tuning
- [x] Margins (5%, -10%) preregistered
- [x] Pilot seeds disjoint from confirmatory seeds (per policy)

### Check 3: Correct Reference
- [x] Compares to no_prior baseline (not self)

### Check 4: Runnable Independently
- [x] Pilot ran successfully 2026-09-04

---

## References

**Authority:**
- TIER1_GATE_STATUS.md lines 106-134 (V11 inconclusive)
- BUILD_PROGRAM_v2.md lines 252-256 (demotion rule)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 797-809 (V11 repair)
- protocols.json lines 27-38 (tier1_gate family), lines 85-94 (power policy)

**Results:**
- validation/results/v11_pilot_summary.json (pilot INCONCLUSIVE)
- validation/results/v11_sizing.json (confirmatory not sized)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol (pilot completed 2026-09-04)
- V11a: INCONCLUSIVE (point=+6.04%, power insufficient)
- V11b: INCONCLUSIVE (point=-2.49%, power insufficient)
- Demotion applied: πBO/PriorBand to opt-in
- Confirmatory blocked: insufficient power at max_sample

---

**END OF PROTOCOL**
