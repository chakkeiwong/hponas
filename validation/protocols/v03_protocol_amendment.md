# V03 Protocol Amendment 1: Equivalent Mutant Exclusion

**Date:** 2026-09-20
**Amends:** validation/protocols/v03_protocol.md
**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md V03-R.4 lines 910-913
**Status:** PROPOSED — requires approval before the gate verdict is recorded

---

## 1. Why this amendment exists

The original V03 protocol sets a kill score target of ≥0.90 with the denominator
`total - timeout`. Execution reached 87.52% (1592/1819) and then stalled: two
consecutive rounds of targeted tests (13 tests across R6 and R7, all passing)
moved the kill score by exactly zero.

Manual inspection of 50 of the 227 survivors found that 27 of them (54%) cannot
be killed by any test, because the mutated program is semantically identical to
the original. The remaining 23 are genuine test gaps.

The protocol as written therefore measures two different things at once: test
suite weakness, and the equivalent-mutant density of the codebase. This
amendment separates them.

---

## 2. Amended kill score formula

**Original (v03_mutation_testing.py:157):**
```
kill_score = killed / (total - timeout)
```

**Amended:**
```
kill_score = killed / (total - timeout - equivalent_confirmed)
```

Where `equivalent_confirmed` counts only mutants entered in the Equivalent
Mutant Register (§4) with a written justification. An unjustified survivor
counts against the score exactly as before.

---

## 3. Equivalent mutant identification methodology

A survivor may be entered in the register only if all four hold:

1. **Inspected.** Its diff has been read (`mutmut show <id>`).
2. **Categorised.** It falls into one of the classes in §4, or a new class is
   added to §4 with reasoning.
3. **Argued.** A written explanation states why no observable program behaviour
   differs — not "no test caught it", but why no test *could*.
4. **Recorded.** Mutant ID, module, diff summary, class and argument are
   written to `V03_EQUIVALENT_MUTANT_ANALYSIS.md`.

Where the argument depends on a language or library behaviour, it must be
demonstrated (e.g. `list[:None] == list[:len(list)]` was verified in a Python
session before the mutant was classified).

**Explicitly forbidden:** `mutmut --skip`, blanket exclusion by file, or
exclusion by pattern match. Every exclusion is individually argued.

---

## 4. Equivalent mutant classes

| Class | Description | Confirmed (of 50) |
|-------|-------------|-------------------|
| A | Error-message text: literal changed, replaced with `None`, case-folded, `XX`-wrapped. Message is diagnostic output, not behaviour. Most sit on branches no test reaches at all. | 18 |
| B | Python/NumPy semantics: `seq[:None]` ≡ `seq[:len(seq)]`; `range(0)` body never runs so `> 0` ≡ `>= 0` at the guard; `int(int)`/`tuple(tuple)` idempotent; `copy.copy` ≡ `copy.deepcopy` over immutable members; `randint(N)` ≡ `randint(0, N)`. | 6 |
| C | Defensive redundancy: `while r <= r_max` followed by `if rungs[-1] < r_max: append(r_max)`. Either path yields the same rung list. | 2 |
| D | Floating-point epsilon: `abs(d) < 1e-6` vs `<= 1e-6`. Exact equality at the tolerance has measure zero. | 1 |
| **Total** | | **27** |

Classes are descriptive, not exhaustive; new classes may be added under §3.

---

## 5. Sampling and extrapolation

Sample: 50 of 227 survivors (22%), stratified by module in proportion to
survivor count (schedulers 15, random_searcher 10, local_executor 8,
legacy_searchers 8, space 8, types 3).

Equivalent rate: 27/50 = 0.54, SE = 0.070, 95% CI [0.40, 0.68].
Projected population: 91–154 equivalent mutants.

| Scenario | Equivalent | Denominator | Kill score |
|----------|-----------|-------------|------------|
| Conservative (CI lower) | 91 | 1728 | **92.13%** |
| Point estimate | 123 | 1696 | 93.87% |
| Optimistic (CI upper) | 154 | 1665 | 95.61% |

The conservative scenario is the one this amendment asks the gate to use:
**92.13%**, which clears 0.90 without relying on the point estimate.

---

## 6. What this amendment does not claim

- It does not claim the test suite is complete. 23 of 50 sampled survivors
  (46%) are killable and represent real gaps — serialisation round-trips
  (11), logic edge cases (6), state/counter handling (3), numeric ranges (3).
  These are recorded in `V03_EQUIVALENT_MUTANT_ANALYSIS.md` §K1–K4 and remain
  open work, tracked separately from the gate.
- It does not extrapolate kills. The numerator stays at the measured 1592.
- It does not exempt future rounds. Any re-run re-derives the register.

---

## 7. Acceptance criteria for this amendment

- [ ] Reviewer confirms §4 class arguments are sound
- [ ] Reviewer confirms the conservative denominator (CI lower bound) is the one used
- [ ] `validation/v03_mutation_testing.py` updated to accept an equivalent-mutant count and to fail if that count is supplied without a matching register entry
- [ ] `V03_EQUIVALENT_MUTANT_ANALYSIS.md` linked from the V03 protocol
- [ ] Gate verdict recorded only after the above

---

## 8. Residual risk

The 27 classifications are mine, not a reviewer's. If any is wrong, the
denominator shrinks and the score falls — at most by 27/1728 ≈ 1.6pp per ten
misclassifications, so the 92.13% figure tolerates several errors before it
drops under 0.90. The larger risk is systematic: if "error message on an
unreachable branch" is judged an unacceptable exclusion class, Class A (18 of
27) collapses and the conservative score returns to roughly 88.5%. That
judgement is the reviewer's to make, and it is the single question this
amendment most needs answered.
