# Hyperparameter Tuning Survey and Product Proposal
**Release date:** 2026-08-26  
**Document:** `main.pdf` (106 pages)  
**Status:** Ready for colleague review

## What this document is

A methods survey and concrete product proposal for a shared hyperparameter
tuning system serving our workspace projects: reinforcement learning (PPO
on RLlib), Hamiltonian neural networks, neural-transport samplers, and
multi-objective financial models.

Two questions answered:
1. Is Ray Tune the right architecture base?
2. Which algorithms should we build?

Two decisions requested:
1. Approve the tier-0 build (wrapping audited components, ~6 engineer-weeks)
2. Fund the tier-1 gate (first method campaign, ~12 weeks total to gate)

## What's inside

**Part I–II (pp. 1–18):** The problem and the running example (PPO's 15-knob
space, expensive/noisy/gradient-free, four workload families).

**Part III (pp. 19–50):** Method chapters with decision boxes — model-free,
Bayesian, multifidelity, population-based, multi-objective, priors/transfer.
Each box verdict now carries an overturn clause naming the observation that
would demote or exclude it.

**Part IV (pp. 51–70):** Our workloads, the library audit, and the
architecture verdict (two interfaces, two adapters, a database; yes to Tune
as the execution layer).

**Part VI (pp. 71–90):** The concrete product proposal:
- Ch11: What we ship (a package on Tune, four workload-shaped studies, not a
  platform) and a day-one walked study at tier 0
- Ch12: The architecture design (unchanged from its earlier argument)
- Ch13: Interfaces and data contracts (study declaration, search-space
  schema with priors first-class, searcher/scheduler interfaces with
  capability flags and population verbs, run store with lineage and standing
  diagnostics, two executor adapters)
- Ch14: The validation suite — 15 numbered tests (V01–V15) collecting every
  falsification promise, three cost layers, statistical protocol, sabotage
  entries, priced campaigns, tier gates with named demotion consequences
- Ch15: The build plan — dependency-ordered calendar (gates at weeks 6, 12,
  30 on one-engineer assumption), rolled-up bill (~42 engineer-weeks; a few
  GPU-weeks of campaign compute), risk register with tripwires

**Register:** `product_register.json` holds all 38 decision-box verdicts with
contract and suite-test anchors filled.

## Quality gates passed

- **Falsifiability:** Every decision box has an overturn section
- **Traceability:** 38/38 verdicts anchored (contract + suite test)
- **Ordering:** No use-before-explain violations (audited mechanically)
- **Readability:** 77 words/concept (inside exemplar band), 12.3% burst
- **Build:** Clean at 106 pages, zero LaTeX errors, citations resolved
- **Ledger:** Five dated revision passes recorded in `literature-audit.md`

## How to read it

- **For the sponsor decision:** Read Ch1 (the questions and short answers),
  Ch11 (what we ship), Table 14.1 (the validation register, p. 82), and
  Ch15's calendar and bill (pp. 86–88).
- **For the build lead:** The whole Part VI is the specification; the method
  chapters (Part III) hold the evidence each contract line cites.
- **For a method challenge:** Find the verdict in Table 2 (p. 64), read its
  decision box, then the chapter section arguing it.

## What's not claimed

- That this is the only viable design (alternatives are noted where they exist)
- That the tier-1 gate will pass on schedule (the suite exists to test that)
- That the population flagship will survive its boundary trial (V08's
  demotion rule was fixed before any code)
- That one case proves general efficacy (this is a workspace-internal tool
  for four known families)

## Next steps if approved

Week 1–2: Freeze interfaces, size pinned tasks to compute envelope, stand up
layer-one harness. Weeks 3–6: Tier-0 build and gate (wrapping + wiring).
First decision point at week 6 when V01–V03, V05, V14 report.

---
For questions: see `literature-audit.md` for the full revision record and
sourcing log.
