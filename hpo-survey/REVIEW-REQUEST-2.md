# Hands-off review request – second round
**Date:** 2026-08-26  
**Document:** `main.pdf` (106 pages, builds clean)  
**Requester:** Survey author  
**Target reader:** Someone who will judge whether this survey is ready to serve as the evidence layer for an HPO product build

---

## What changed since the first review

Four material corrections from your feedback, all now applied:

1. **M1 (GP noise)** — The figure caption and body text now state that the "interpolation" and "variance collapses to zero" claims hold only in the noiseless limit; with $\sigma^2 > 0$ the mean passes *near* observations and the variance stays positive everywhere. The caption adds: "The figure is drawn in the low-noise regime for legibility." The body paragraph after equation (4.2) now clarifies that once kernel hyperparameters are estimated by marginal likelihood, observed *values* do influence the variance indirectly through those fitted parameters, so "the model knows where it is ignorant before it knows what the answer is" is conditional on fixed hyperparameters.

2. **M2 (decade arithmetic)** — Fixed. The interval $[10^{-5}, 10^{-2}]$ spans *three* decades (−5 to −4, −4 to −3, −3 to −2), not four. Chapter 3 now reads "a log-uniform draw spends a third of its budget in each of the three decades."

3. **M3 (Chebyshev completeness)** — Qualified. The text now states that the standard completeness theorem uses the *true* utopian point and requires convexity or boundary assumptions; using the best-seen point (as we do operationally) is an approximation that improves coverage over weighted sums but lacks the theoretical guarantee.

4. **M4 (πBO zero support)** — Clarified. The decay formula now includes "for every $\config$ in the prior's support," and the next sentence explicitly states "Points assigned zero prior probability stay at zero." This makes it clear that πBO does not escape a prior that rules out the true optimum.

Additionally: **S1 (the running example's conditional knob)** — corrected throughout. The 15-knob PPO space from BG-PBT (Wan+ 2022) contains *no* conditional structure; it is a flat mixed space. The "soft-update temperature conditional on its switch" that appeared in earlier drafts was an off-policy RL knob from a *different* workload family (Chapter 9, the Acme agents). I've removed every mention of soft updates from the running example, replaced it with "annealing off" (learning-rate annealing, which *is* conditional and appears in Chapter 2's workload catalog but not in the 15-knob joint space), and updated Chapter 14's product walkthrough to state explicitly that the BG-PBT study declares a flat space while the conditional-structure test lives in the annealing and off-policy workloads.

---

## What you're being asked to read

The same thing as last time, now with those five errors fixed:

- **Does this document teach its methods linearly** — can a reader who knows optimization and some ML follow the derivations, understand why each method exists, and reconstruct the verdicts without already believing them?
- **Is the four-angle structure doing work** — do the closing sections of Chapters 3–8 actually argue from different epistemic positions (arithmetic, experimental replication, failure-mode testing, resource constraints), or are they template-filling?
- **Are the verdicts checkable** — does every "include X, exclude Y" claim in the decision boxes cite the chapter that justifies it, and does that chapter contain the promised evidence?

You don't need to verify the math or audit the citations (the literature-audit ledger tracks that). You're reading for **coherence**, **teachability**, and **honest argumentation**.

---

## How to flag problems

Same process: material errors get an **M** label, style/clarity issues get an **S** label, and anything you're uncertain about gets flagged anyway with a note. I'll address every **M** issue before the document is considered review-complete.

---

## Build status

```
errors: 0  overfull: 0  undef: 0
(106 pages)
```

The document is ready to read.
