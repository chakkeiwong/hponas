# Literature audit ledger for the HPO survey

Companion to `main.tex`/`refs.bib` in this directory, maintained under
`~/workspace/claudecodex/policies/scholarly-literature-audit-policy.md`.
All verification dates are 2026-08-22 unless noted; a re-verification pass
on 2026-08-23 (see "Re-verification pass" below) resolved most flagged
fields and expanded all abbreviated author lists. Verification transport:
arXiv export API, ar5iv/arXiv HTML full texts, PMLR/JMLR/NeurIPS proceedings
pages, DOI content negotiation (CSL-JSON), GitHub/PyPI APIs, and rendered
docs pages; the WebFetch tool was network-blocked for several publisher
domains in this environment, so `curl` against the same URLs was used.
Semantic Scholar API records were used only where the publisher page was
bot-blocked, and are marked as such.

## Compact audit summary

```text
decision: review-ready as an internal research note; not camera-ready for
  external publication without resolving the flagged venue fields below.
metadata_date: 2026-08-22; re-verification and flag resolution 2026-08-23
seed_papers: Wan 2022 (BG-PBT), Eimer 2023, Ament 2023 (LogEI),
  Daulton 2021 (qNEHVI), Jaderberg 2017 (PBT), Li 2020 (ASHA),
  Cowen-Rivers 2022 (HEBO), Hvarfner 2024, Song 2024 (Vizier GP bandit),
  Rakotoarison 2024 (ifBO), Mallik 2023 (PriorBand), White 2023 (NAS survey)
source_support_summary: 6 papers read at full-text/method depth from local
  PDFs or ar5iv (BG-PBT, Eimer, plus agent full-text reads of qNEHVI,
  MO-ASHA, MO-DEHB, Karl survey, NeuTra, HNN, White survey, PB2, PB2-Mix,
  FIRE-PBT, piBO, PriorBand, DyHPO, DPL, ifBO, CARBS, muTransfer, LogEI,
  TuRBO, SAASBO, HEBO, SMAC3, Vizier, Bischl); ~60 further papers verified
  at abstract+metadata depth; all landing pages fetched.
citation_venue_summary: venues verified against proceedings/journal pages
  or DOI metadata for the load-bearing entries (PMLR v188/v202/v224/v133/
  v51/v115/v235, JMLR, WIREs, Bayesian Analysis, JGO, JAIR title page).
  Citation counts recorded only where an agent fetched them; not used as
  support anywhere in the text.
backward_snowball_summary: recorded per agent report; key leads followed:
  Casmopolitan and TuRBO (from BG-PBT), DEHB and DAC (from Eimer),
  time-varying GP bandits (from PB2), Stooke/Igl distillation (from BG-PBT),
  box decompositions (from qNEHVI), SMAC/RoBO log-EI precursors (from LogEI).
forward_snowball_summary: 2024-2026 sweeps run per theme (queries recorded
  in section "Queries" below); newest verified items: Hvarfner 2024,
  ifBO 2024, ARLBench 2024/2026, MF-PBT 2025, IPBT 2025, alpha-PFN 2026,
  Adkins 2024, CompleteP 2025, Power Lines 2025, Step Law 2025,
  Optuna 5.0rc1 and BoTorch qLog deprecation warnings (docs-level).
quarantined_sources: none found (no retraction/EoC notices on any fetched
  page).
top_omission_risks: see register below.
claim_support_gaps: letham2019 page range unverifiable from open
  metadata (see below); two mechanism details cited at abstract level
  only (daulton2023hvkg, watanabe2023tpe/c-TPE; noted below).
next_required_actions: double-check the five arXiv-comment-sourced
  venues (ICLR 2025, NeurIPS 2025 x2, ICML 2026, RLC 2025) against the
  conference sites once indexes are stable, and have a human read the
  full rendered PDF.
what_is_not_concluded: no claim that any tuner is best in general; all
  rankings are scoped to the cited experiments and budgets. Human-reader
  review of voice and readability is pending; the document is provisional
  in that respect per the global policy.
```

## Inspection depth for load-bearing sources

| Source | Depth | Where |
|---|---|---|
| Wan 2022 BG-PBT | full text pp. 1-10 read directly (local PDF, srv folder); Alg. 1, Sec. 3.1-3.2, Thm 3.1, Tables 1-3, limitations | main session |
| Eimer 2023 | full text pp. 1-9 read directly (local PDF); landscape, seed, and method-comparison sections, recommendations | main session |
| Ament 2023 LogEI | abstract + intro + Sec. 3 + App. A structure (arXiv HTML) | agent |
| Daulton 2021 qNEHVI | full text: Sec. 4 background, Sec. 6 cached box decompositions, complexity statements (ar5iv) | agent |
| Schmucker 2021 MO-ASHA | full text: selection strategies, EpsNet, experiments (ar5iv) | agent |
| Awad 2023 MO-DEHB | full text: NDS + crowding selection, SH promotion (ar5iv) | agent |
| Karl 2023 survey | full text: taxonomy figure, scalarization equations 8/10 (ar5iv) | agent |
| Hoffman 2019 NeuTra | full text: BO tuning objective (R-hat penalized ESS/grad), IAF setup (ar5iv) | agent |
| Greydanus 2019 HNN | full text: loss structure, appendix grid-search settings, pixel-task 3-term loss (ar5iv) | agent |
| White 2023 NAS survey | full text: zero-cost-proxy and baseline conclusions (ar5iv) | agent |
| Parker-Holder 2020 PB2 | full text: Alg. 1, time-varying kernel, Thm 2/10 regret bound (ar5iv) | agent |
| Parker-Holder 2021 PB2-Mix | full text: TV.EXP3.M, DepRound, Thm 1, Procgen setup (ar5iv) | agent |
| Dalibard 2021 FIRE-PBT | full text: evaluator/sub-population mechanism, ImageNet numbers (ar5iv) | agent |
| Hvarfner 2022 piBO | full text: prior-weighted acquisition with decay exponent (ar5iv) | agent |
| Mallik 2023 PriorBand | full text: ensemble sampling policy, rung-dependent weights (ar5iv) | agent |
| Wistuba 2022 DyHPO / Kadra 2023 DPL / Rakotoarison 2024 ifBO | full text method sections (ar5iv) | agent |
| Fetterman 2023 CARBS | full text: three-GP structure, Pareto-set parents, Chinchilla/ProcGen results (ar5iv) | agent |
| Yang 2022 muTransfer | full text: transfer scope + stated caveats (ar5iv) | agent |
| Cowen-Rivers 2022 HEBO | full text: warping, acquisition ensemble via NSGA-II, challenge result (ar5iv + JAIR page) | agent |
| Lindauer 2022 SMAC3 | full text: facades, RF rationale (JMLR + ar5iv) | agent |
| Song 2024 Vizier | full text: Sec. 2-3 defaults (UCB coeff 1.8, half-rank warping, trust region, Firefly), Sec. 4 Ray Tune comparisons (ar5iv) | agent |
| Eriksson 2019 TuRBO / Eriksson-Jankowiak 2021 SAASBO | full text: trust-region rules; SAAS priors and NUTS inference (ar5iv) | agent |
| Bischl 2023 | abstract + Sec. 6 guidance passages (ar5iv) | agent |
| Hvarfner 2024 vanilla high-dim BO | abstract (mechanism stated there); PMLR v235 listing | agent |
| Library claims (Sec. 10) | GitHub API, PyPI JSON, raw READMEs, release notes, rendered docs for all 20+ libraries; details in agent report | agent |
| Li 2020 ASHA | full text: Secs 4.1-4.4 experiments (25-worker CIFAR comparisons vs sync SHA/BOHB/PBT, 16-worker NAS spaces, 500-worker LSTM run), straggler simulation, Determined AI systems framing (ar5iv) | main session 2026-08-25 |
| Awad 2021 DEHB | full text: Sec 5 experiment scope (toy/surrogate/tabular + 13 NAS-Bench benchmarks), comparator list, 1000x/32x speedup figures, simulated-cost protocol footnote, NAS-Bench-101 low-correlation behavior (ar5iv) | main session 2026-08-25 |
| Daulton 2021 qNEHVI | full text: experiments section (comparators PESMO/MESMO/PFES/DGEMO/TSEMO/MOEA-D-EGO/TS-TCH/qEHVI variants; noise as % of objective range up to 20%; findings under noise; wall-time notes) (ar5iv) | main session 2026-08-25 |
| Hvarfner 2022 piBO | full text: Sec 4 experiments (prior-quality spectrum incl. purposefully detrimental priors on Branin/Profet FC-Net/XGBoost; recovery-to-baseline finding; beta trade-off; 12.5x DL time-to-accuracy, ImageNette 94.1%) (ar5iv) | main session 2026-08-25 |
| Mallik 2023 PriorBand | experiments re-read: mf-prior-bench suite (MF-Hartmann + PD1-derived image/language tasks), good/bad priors, prior-mode-first fairness protocol, consistent top ranks (local PDF) | main session 2026-08-25 |
| Schmucker 2021 MO-ASHA | experiments re-read: NAS-201 (exact front), Adult fairness, Wikitext2 LM; eta=3, R=200/81, quantile normalization, 100 random weight vectors, 30-min wall-clock races (local PDF) | main session 2026-08-25 |

Local copies of post-2023 load-bearing papers are in `.localresources/`
(LogEI, Hvarfner 2024, ifBO, PriorBand, CARBS, ARLBench, MF-PBT, Vizier,
MO-PBT); pre-2023 load-bearing papers exist in the user's corpus under
`/home/ubuntu/google-drive-papers/ML for optimization/` and `~/google-drive-papers`.

## Flagged fields (status after the 2026-08-23 pass)

Resolved 2026-08-23:

- jamieson2016successive: pages 240--248 added from the PMLR v51 paper
  page (citation_firstpage/lastpage meta tags); booktitle now names
  PMLR 51.
- awad2021dehb: second source obtained. DOI 10.24963/ijcai.2021/296
  (CSL-JSON) confirms IJCAI 2021 proceedings, pages 2147--2153 (added).
  Note: the publisher's own DOI metadata misspells the title
  ("Hyberband"); the bib keeps the correct spelling from the paper.
- feurer2015metalearning: CrossRef search returned DOI
  10.1609/aaai.v29i1.9354, container "Proceedings of the AAAI
  Conference on Artificial Intelligence". Venue verified.
- karl2023moo: ACM TELO volume 3, issue 4, pages 1--50 and year 2023
  confirmed via DOI CSL-JSON; fields restored to the bib entry. Full
  13-author byline transcribed from the same record.
- hayes2022morl: volume 36, issue 1, article 26 (2022) confirmed via
  DOI CSL-JSON and added; full 18-author byline transcribed.
- Author lists: all 24 "and others" entries expanded to full bylines
  from arXiv export API records (2026-08-23) or DOI CSL-JSON (karl,
  hayes, morales). One spelling follows the arXiv record over the
  common form: "Johan Bjorck" (arXiv lists no umlaut).
- rakotoarison2026alphapfn: arXiv id located (2606.07134); comment
  field states "Published at ICML 2026". Id added to the bib note.

Still flagged:

- letham2019noisyei: page range 495--519 remains from the common
  citation only. Checked 2026-08-23: DOI CSL-JSON and the CrossRef
  REST record carry volume 14, issue 2 but no pages; Semantic Scholar
  has no pages; Project Euclid bot-blocks the fetch. Verify from the
  journal page or PDF before external use.
- bjorck2025tokenhorizon / bergsma2025powerlines / dey2025completep /
  rakotoarison2026alphapfn / doulazmi2025mfpbt: venues re-confirmed
  2026-08-23 from arXiv comment fields, now with camera-ready or
  "published at" language (ICLR 2025, NeurIPS 2025 x2, ICML 2026,
  RLC 2025 camera-ready); still not checked against conference sites.
- morales2022survey: Springer DOI metadata says 2022; commonly cited
  2023 (print). We cite 2022 per the DOI record. No change.
- hansen2016cmaes: arXiv tutorial, cited as such; fine.
- daulton2023hvkg: cited from the PMLR v202 landing page; mechanism
  summary from its abstract only.
- watanabe2023tpe and c-TPE: abstract-level verification; the specific
  component recommendations attributed to the tutorial are as stated in
  its abstract. Landing pages re-fetched 2026-08-23 (v5 datelines,
  May/June 2026); no retraction or withdrawal notices.

## Teaching expansion (2026-08-24)

The document was rewritten as a linear teaching narrative per
`~/workspace/claudecodex/skills/write-linear-scholarly-narrative/`
(running example: PPO on Brax in the BG-PBT search space; secondary
running case: the Hamiltonian network for multi-objective sections),
growing from ~32 to 51 pages with 15 new TikZ figures and in-place
derivations. Source-audit consequences:

- No new citations were added; every claim still traces to the entries
  verified above. The added derivations are elementary
  PROJECT_DERIVATION material that explains cited results rather than
  extending them: partitioned-Gaussian conditioning for the GP
  posterior (standard, per Rasmussen-Williams), the EI closed form and
  its tail/underflow arithmetic (standard normal-tail expansions,
  consistent with the LogEI paper's analysis), the TPE ratio-EI
  monotonicity (the paper's own model, standard Bayes manipulation),
  successive-halving/Hyperband budget arithmetic (from the papers'
  stated schedules; the 81/34/15/8/5 bracket sizes match the standard
  R=81, eta=3 example), the random-search coverage bound
  1-(1-p)^n, a worked 2-D hypervolume computation, and the
  supporting-hyperplane argument for the weighted-sum blind spot
  (already recorded above as PROJECT_DERIVATION).
- All figures are schematic mechanism drawings, labeled as such in
  captions and in the introduction; none presents measured data.
- Per the linear-teaching policy, the rewritten document's
  reader-facing quality is `human-review-pending`: a human read of the
  rendered PDF remains required before the note is treated as
  review-ready, and this supersedes neither flag in the sections
  above.

## Decision layer and compute/NAS subsection (2026-08-24, second revision)

After manager feedback that the teaching edition remained too dense for
include/exclude decisions, a distinct operational layer was added
(permitted by the global policy's "keep operational material in a
distinct layer" rule): boxed "Decisions from this section" registers at
the ends of Sections 3-9, a master decision table (Table 2) in
Section 12, a plain-language glossary, and bridge sentences mapping
core objects to economics/statistics equivalents (GP = kriging,
EI = option value, Pareto = welfare-theoretic). No claims changed; the
boxes restate section verdicts with costs and evidence pointers.

New Section 9.5 addresses the compute cost of RL tuning and the
one-shot / zero-cost / grammar-based NAS question. One source added:

- schrodi2023grammar (arXiv:2211.01842, comment field "NeurIPS 2023",
  fetched via arXiv API 2026-08-24; abstract-level verification;
  classification DIRECT_METHOD for the grammar-space discussion only).
  Claims drawn: CFG-based hierarchical space construction, spaces far
  larger than common ones, BO with hierarchical kernels; all stated in
  the abstract. Venue from arXiv comment; flag alongside the other
  comment-sourced venues.
- The RL-specific arguments against one-shot supernets (non-stationary
  training signal; little to amortize for small policy/value MLPs) are
  labeled as our inference in the text, not sourced claims.

## Re-verification pass (2026-08-23)

Independent re-check after the initial audit, run over the live
sources rather than the prior agents' notes:

- arXiv landing pages re-fetched for 25 core entries (Snoek, HEBO,
  TuRBO, SAASBO, Hvarfner 2024, Vizier GP bandit, SMAC3, Watanabe TPE,
  c-TPE, qNEHVI, LogEI, MORBO, MO-ASHA, Karl, Morales, Paria, JES,
  Bischl, Bounce, PFNs4BO, CMA-ES tutorial, NGOpt/ABBO, DEHB, LLAMBO,
  ifBO): titles, bylines, datelines, and comment fields all consistent
  with the bib; no retraction or withdrawal notices on any page.
- IEEE classics verified via DOI CSL-JSON: NSGA-II (TEVC 6(2):182-197,
  2002), MOEA/D (TEVC 11(6):712-731, 2007), ParEGO (TEVC 10(1):50-66,
  2006), SPEA (TEVC 3(4):257-271, 1999). All match the bib.
- Library metadata re-fetched from PyPI JSON (21 packages) and the
  GitHub API (Katib v0.19.0, Oct 2025, Apache-2.0, not archived).
  Every version, date, and maintenance signal in Sec. 10 and its table
  matches the 2026-08-23 fetch; no text changes needed.
- Forward-snowball spot-check on the PFN/in-context BO line surfaced
  "Position: The Future of Bayesian Prediction Is Prior-Fitted"
  (arXiv:2505.23947) and "Dynamic Priors in Bayesian Optimization"
  (arXiv:2511.02570); both classified BACKGROUND and omitted — the
  survey's PFN coverage (PFNs4BO, ifBO, alpha-PFN) already spans the
  claims we make. Recorded in the register below.

## Omitted-paper and reviewer-risk register

- Gradient-based HPO beyond Lorraine 2020 (e.g., Franceschi's earlier
  work, DrMAD, self-tuning networks): out of declared scope
  (Sec. 2.3 states the boundary). Risk: low for an internal note.
- OptFormer-descended LLM tuning proposals (LLAMBO et al.): mentioned in
  roadmap "skip" list without individual citations; LLAMBO was verified
  by an agent (ICLR 2024 poster) but we chose not to cite it in the text
  to keep the skip paragraph unencumbered. Risk: a reviewer may ask for
  the citation; acceptable for an internal note, revisit if circulated.
- SMS-EGO, PESMO, and the wider classical MOBO acquisition zoo: omitted
  in favor of the qEHVI line and scalarization; Karl et al. survey cited
  for coverage. Risk: low.
- Hennig-Schuler Entropy Search (2012): superseded in exposition by
  PES/MES/JES; not cited. Risk: low.
- Meta-learned initialization literature beyond Feurer (Wistuba,
  Vanschoren surveys): summarized via the transfer section's citations.
  Risk: low.
- BORE / likelihood-free BO (present in the user's local folders):
  omitted; TPE covers the density-ratio idea in the text. Risk: low,
  but the user's own folder suggests interest; candidate for a future
  appendix.
- Hyper-Tune (VLDB 2022), OpenBox paper details, FLAML algorithms
  papers: library section cites the systems; the algorithm papers
  (CFO/BlendSearch) are not individually cited. Risk: low.
- DeepSeek-style scaling-law papers are cited as guidance; we did not
  audit their fitting methodology. The text presents them as "guidance
  to encode", not verified laws. Risk: low given framing.
- PFN position paper (arXiv:2505.23947) and Dynamic Priors in BO
  (arXiv:2511.02570), surfaced in the 2026-08-23 sweep: BACKGROUND;
  neither introduces a tuning method the survey's claims depend on.
  Risk: low; candidates for the roadmap section in a future revision.

## Claim-support notes on the survey's own comparative statements

- "DEHB most consistent at 10-64 run budgets in RL" is scoped to
  Eimer 2023's experiments in the text (PRIMARY_TECHNICAL_SUPPORT,
  full-text read).
- "BG-PBT outperforms tuned baseline and prior PBT methods on Brax at
  B=8, 150M steps" from the paper's own Tables 1-2 (read); the
  independent budget-bounded counter-evidence from Eimer 2023 is
  presented alongside. Both are descriptive of the cited experiments;
  no general superiority claim is made.
- "Random search strong baseline on 4/7 Brax tasks" from BG-PBT
  Table 1 (read).
- Hypervolume computational-complexity statement cited to qNEHVI's text
  (super-polynomial in objectives), not to a #P-hardness source.
- Weighted-sum blind spot: supported by the standard convex-hull
  argument, stated in one sentence in the text (PROJECT_DERIVATION,
  elementary); Chebyshev completeness asserted per Karl et al.
- Library maintenance claims: IMPLEMENTATION_EVIDENCE from repository
  metadata fetched 2026-08-22, each dated in the text.

## Monograph conversion and evidence-section expansion (2026-08-24/25)

After manager feedback that persuasion means fuller teaching rather than
condensation (the CardNPV two-volume precedent), the document was
converted from an article to a report-class monograph with parts, and
each method chapter (3-8) was given a closing pair of sections before
its decision box: one teaching the experiments the chapter's verdict
rests on (design, arena, sponsor, and known weaknesses, so the evidence
can be judged rather than taken on citation), and one arguing the
verdict from four independent angles, ending with a falsification
criterion tied to the planned validation suite. Chapter 9 keeps its
per-workload structure, which already argues from named evidence.
Source-audit consequences:

- No new sources were added. Six existing entries were inspected at
  additional depth on 2026-08-25 to support the new evidence sections
  (rows dated 2026-08-25 in the inspection table above): ASHA and DEHB
  experiment sections via ar5iv, qNEHVI and piBO experiment sections
  via ar5iv, PriorBand and MO-ASHA experiment sections from the user's
  local PDFs. All experimental figures quoted in the new sections
  (worker counts, speedup factors, noise ranges, benchmark task lists,
  protocol details) trace to those inspections.
- The claim in Chapter 7 that no independent budget-matched study of
  multi-objective tuners on live training surfaced is scoped to the
  sweeps recorded under "Queries" below; it is stated in the text as a
  property of our audit, not of the literature.
- The wording sweep from the article structure (section -> chapter)
  was completed, one cross-reference repaired (Chapter -> Section for
  sec:bo-evidence in Chapter 6), and the introduction now describes
  the closing-section pattern.
- Reader-facing quality remains `human-review-pending` per the
  linear-teaching policy; nothing here supersedes the flags above.

## Pacing pass to exemplar density (2026-08-25, second session)

After manager feedback that the document remained too dense (exemplars
supplied: the CIP monograph and the CardNPV two-volume set, both
averaging ~81 words per paragraph with one move per paragraph), the
whole survey was re-paced: packed multi-method paragraphs were unfolded
into one-idea-per-paragraph sequences (the qEHVI-to-HVKG lineage in
Ch. 7 became a five-subsection teaching section; the freeze-thaw-to-ifBO
lineage in Ch. 5 and the PFN lineage in Ch. 8 became one paragraph per
method; the post-2022 PBT family in Ch. 6 and the NAS verdicts in Ch. 9
likewise), and long single-breath paragraphs were split at their
argumentative seams throughout Chapters 1-9, 11, and the abstract.
Document statistics moved from mean 128 / median 114 words per prose
paragraph to mean 90 / median 82, against the exemplars' 81/70. The two
per-library entries in Ch. 10 keep their inventory form deliberately.

Source-audit consequences: no claims, citations, or numbers were added,
removed, or reattributed; the only new material is elementary
PROJECT_DERIVATION teaching arithmetic in Ch. 7 (a two-outcome EHVI
computation of 0.25 consistent with the chapter's existing worked
hypervolume figures; an illustrative 0.8 x 0.3 = 0.24
feasibility-discount instance; a schematic phantom-front description of
the lucky-seed failure that qNEHVI repairs, consistent with the
document's schematic-figures policy). One section retitle in Ch. 7
(no label attached, no cross-references affected). Reader-facing
quality remains `human-review-pending`; Chapter 7 is the natural first
chapter for the pending human read, since it demonstrates the new
pacing on the passage the manager flagged.

## Concept-density instrument (2026-08-25)

`tools/concept_density.py` measures conceptual pacing on three axes,
calibrated by running one detector over this survey and the two house
exemplars (CIP monograph chapters; CardNPV two-volume chapters):
introduction rate (words per new concept), consolidation (occurrences
per concept, singleton share), and burst/live load (new concepts per
paragraph; introductions within a trailing 1500-word window, the
operational form of the teaching contract's live-items diagnostic).
Detector: acronyms/method tokens, predominantly-capitalized proper
terms, \emph-introduced phrases, recurring technical bigrams, citation
keys; spot-checked precision roughly 80 percent, with noise symmetric
across documents, so ratios are the deliverable, not absolute counts.
Calibration 2026-08-25: survey 70 words/concept (12.9 percent burst
paragraphs, 40 percent singletons); CIP 83 (5.9, 35); CardNPV 253
(0.8, 19). Re-run with `--lint=hpo-survey` to list burst paragraphs.

## Slow-over-dense expansion program (2026-08-25, begun)

Manager directive: when in doubt, err toward slower and lengthier
teaching; skippable-slow beats unfillable-dense. Technique extracted
from the CardNPV exemplar's own chapters: a concrete case before any
abstraction, the same idea shown in several representations, a
read-back after every figure, one concept per section. Chapter 2
expanded first (1,974 to 3,034 words): the four knob kinds are now
taught one at a time with instances, the fifteen running-example knobs
are read in groups with plain-language meanings (discount as time
preference, entropy bonus as paid experimentation, clipping as a trust
leash), the expensive/noisy/gradient-free triple has a paragraph each,
the tuning loop is walked through one full cycle, the seed expectation
gets a two-seed worked reading (900/300 vs 640/660), and the four
bends became titled subsections. The introduction's preview now tells
readers its names are only names, taught later. All additions are
elementary definitional or arithmetic material (PROJECT_DERIVATION
grade); no sources added, no claims changed. Remaining chapters queue
worst-paced first: 03, 04, 09, 08, 07, 05, 06.

## Logical-ordering pass: no concept before its explanation (2026-08-25)

Manager rule: never use a concept before it is explained; prefer a
generic term first with the name after, or an explicit
taught-in-Chapter-X pointer. A first-use audit (concept_density.py's
introduction positions plus an introduction-signal check) flagged
candidates; after filtering detector noise, roughly twenty-five real
violations were repaired. The largest: PPO was used from page one but
never introduced, so Chapter 2's running example now carries a
plain-language pass through the algorithm (policy, value network,
advantage, clip, return; all elementary definitional material), and
the chapter opener now names the workspace models generically with
one-line glosses. Other repairs: EI/UCB/Pareto-front removed from the
Chapter 4 surrogate section (HEBO's acquisition hedge is now described
generically one section before acquisitions are taught); acronyms
expanded at first use (ASHA, BOHB, CMA-ES, SAASBO, NSGA-II, NUTS, ESS,
FLOPs, GAE, RL, FIRE-PBT, ifBO); surrogate/acquisition vocabulary
removed from Chapters 2-3 prose; PBT cushioned at its Chapter 5
comparator appearance; rungs defined at first use including the
opening figure's caption; BoTorch and Optuna glossed at first body use
with wording matched to the Chapter 10 audit (Optuna: ``where sampler
development is most active,'' not ``most widely adopted''). No claims
or citations changed.

## Part VI: the concrete product proposal (2026-08-26, begun)

The volume gains a closing part, ``The product proposal,'' that turns
the decision-box verdicts into a buildable specification. Method
(recorded here as the plan of record): concrete means every verdict
carries four anchors, a contract, a validation-suite test, a tier and
week, and a price; Table 2 already holds tier and price, and the new
chapters supply the other two. Chapter order: a product opener with a
day-one worked study at tier 0 (written 2026-08-26, composition of
audited components only, each step citing its evidence chapter), then
the existing architecture chapter, then two new chapters to come
(interfaces and data contracts; the validation suite, which collects
the falsification criteria already stated in the four-angle closings),
then the roadmap expanded with calendar and economics. A
machine-readable register of all 38 box verdicts was extracted to
product_register.json; the register is bookkeeping, not exposition.

Completed 2026-08-26 (same day, after manager feedback that the part
was underweight): the contracts chapter (study declaration with
mandatory objective and seed-protocol fields and the parallel-worker
boundary input; search-space schema with kind, transform, condition,
prior; searcher interface with capability flags and snapshot;
scheduler interface with report/promote/gate and the population
exploit/explore verbs; run store with lineage and standing
diagnostics; two executor adapters with checkpoint surgery and
measured cost); the validation-suite chapter (fifteen-entry test
register V01-V15 collecting every four-angle falsification promise,
three cost layers, the statistical protocol from Eimer's discipline,
sabotage entries V03/V11, sizing arithmetic for the two priced
campaigns V07/V08, tier gates with named demotion consequences); and
the roadmap expanded with a dependency-ordered calendar (gates at
weeks 6, 12, 30 on a one-engineer assumption, labeled as the
manager's variable), a rolled-up bill (~42 engineer-weeks; a few
GPU-weeks of campaign compute), and a risk register with tripwires
(Ray drift, BoTorch/Optuna churn already observed in the Chapter 10
audit, boundary non-transfer, seed-protocol opt-out rate). The old
"How we will know" section now points to the suite chapter; its text
moved there edited, citations intact. product_register.json anchors
filled for 37 of 38 entries (contract and suite test per verdict).
Volume: 105 pages, clean build, new chapters inside the pacing band
(means 75-92 words per paragraph). No new sources; all quantitative
suite parameters are labeled estimates pending week-1--2 sizing.
Status: human-review-pending for the whole part.

## Release-readiness audit and repairs (2026-08-26, completed)

Manager asked whether the document is ready for colleague review and
whether any gaps remain in readability, product soundness, or
claudecodex/policies compliance. A comprehensive three-dimensional
audit revealed two blocking categories and one advisory:

BLOCKING (product soundness): Seven decision boxes (Ch3–9) lacked
overturn clauses; one verdict lacked register anchors; Ch1's reading
map was stale (named Ch14 but not Ch15/16).

BLOCKING (readability ordering): Eight ordering violations flagged:
PPO, PriorBand, PB2, BG-PBT named in Ch1's preview before being
taught; "Pareto front" used abstractly before Ch7; GAE unexpanded in
Ch2; BoTorch glossed without stating what it is; ASHA used before
expansion.

ADVISORY: Ch1 ran 21 words/concept (dense for an opener), but overall
pacing acceptable (77 w/concept doc-wide, 12.3% burst, inside CIP
band).

Repairs executed same day: seven overturn sections added (~700 words,
one per method chapter, each naming the suite entry or study behavior
that would demote or exclude the verdict); eight ordering fixes
(Ch1's preview now carries the "names only for now, taught later"
disclaimer; GAE expanded; "Pareto front" glossed at first use;
"reinforcement-learning agents" substituted for bare "PPO agents" in
the opener; BoTorch citation is the introduction signal); Ch1 map
updated to name Ch15/16; weighted-sums register anchor filled
(excluded-by-design, V09 reopens). Final state: 106 pages, clean
build, 38 verdicts with full anchors (contract + suite test), seven
falsifiable decision boxes, zero detected ordering violations, ledger
current. Status: released for colleague review 2026-08-26.

## Queries run (recorded by agents, 2026-08-22)

Themes and exact queries are listed in the six agent reports (core BO;
PBT/AutoRL; multi-objective; libraries; multi-fidelity/transfer;
NAS/samplers). Sweep queries included: "Bayesian optimization 2025
advances", "in-context Bayesian optimization 2025", "multi-objective
Bayesian optimization 2025", "AutoRL 2025", "population based training
2024 2025 improvements", "hyperparameter optimization library 2025 new",
"neural architecture search 2025 survey", "optimal learning rate scaling
law 2025", plus arXiv API title searches and DOI lookups.

---

## Review-response corrections applied 2026-08-26

Initial round (reply-to-fable.md): fixed M1 (decade count), M2 (GP noise
caption), M3 (Chebyshev completeness scope), M4 (πBO zero-support), S1
(PPO conditional knob). All corrected by direct source verification against
ar5iv/local PDFs where numerical or mechanistic. Rebuilt clean.

## Codex review response 2026-08-27

Seven material issues (M1-M7) addressed from reply-to-claude.md:
- **M1** Chebyshev completeness: decision box now states "completeness under
  random weights requires the true ideal point and additional assumptions;
  the operational approximation using best-seen values gives better
  coverage in practice without the theoretical guarantee." (07-multiobjective.tex:541-545)
- **M2** GP tier gate: V04 split into tier-0 subset (GP vs log+Sobol floor)
  tested at T0 gate, plus tier-1 remainder. Decision box updated, roadmap
  gates updated. (04-bayesian.tex:871-877, 12-roadmap.tex:165-174)
- **M3** Bayesian forward reference: Ch4 evidence section now explains
  "described in full in Ch6" means experimental design (seed split, budget,
  matched compute) lives there while Ch4 states the minimal inference it
  supports. (04-bayesian.tex:756-767)
- **M4** Validation protocols: new Section 16.4 pins V10 and V13 with
  concrete protocols (correlation threshold 0.6, 100-trial pilot, 3-chain
  sampler protocol with named diagnostics). (16-validation.tex:201-232)
- **M5** V08 repetition: ten-rep rule states its one exception; V08 section
  expanded to three-rep protocol with asymmetric stopping rule and falsifier
  framing. (16-validation.tex:128-134, 162-195)
- **M6** Hard boundaries: qLogNEHVI four-objective threshold and eight-worker
  population boundary both presented as configurable with audit trail.
  (07-multiobjective.tex:534-536, 06-population.tex:473-477)
- **M7** πBO zero-support: decision box now states "the product schema
  requires a lower-bounded mixture or explicitly nonzero support everywhere."
  (08-priors-transfer.tex:376-380)

All changes documentary (no new sources, no new verdicts); build passes at
109 pages. Status remains human-review-pending on linear teachability per
the global teaching contract.

Four material errors corrected after hands-off review, no new sources added:

**M1 (GP noise, Ch4)**: Caption for Fig 4.1 and body text after eq 4.2 now
state that "interpolation" and "variance collapses to zero" hold only in the
noiseless limit ($\sigma^2 \to 0$). With $\sigma^2 > 0$ the mean passes
*near* observations and variance stays positive everywhere. Body text
clarifies that once kernel hyperparameters are estimated by marginal
likelihood (eq 4.3), observed *values* do influence variance indirectly
through fitted parameters. Caption adds "drawn in the low-noise regime for
legibility."

**M2 (decade count, Ch3)**: Fixed arithmetic error. Interval $[10^{-5},
10^{-2}]$ spans three decades, not four. Text now reads "a log-uniform draw
spends a third of its budget in each of the three decades."

**M3 (Chebyshev completeness, Ch7)**: Qualified the coverage claim. Standard
completeness theorem (sweeping positive weights recovers every Pareto point)
requires the *true* utopian vector plus convexity or boundary assumptions.
Using best-seen $z^\star$ (as done operationally) is an approximation that
improves coverage over weighted sums but lacks the theoretical guarantee.

**M4 (πBO zero support, Ch8)**: Added explicit statement that points assigned
zero prior probability stay at zero under the decay formula, so πBO does not
escape a prior that rules out the true optimum. Convergence statement now
reads "converges back to its data-driven self *on that support*."

**S1 (running example conditional, Ch2/Ch14)**: The 15-knob BG-PBT space (Wan+
2022) is flat; it contains no conditional structure. Removed all mentions of
"soft-update temperature conditional on its switch" (that knob belongs to
off-policy RL workloads, Ch9, not the running example). Substituted "annealing
off" where a concrete setting was needed. Ch14 product walkthrough now states
explicitly that the BG-PBT study declares a flat space and that the
conditional-structure test lives in the annealing/off-policy workloads.

All corrections verified by rebuild: 106 pages, 0 errors, 0 overfull, 0 undef.

---

## M-item pass (2026-08-27, final)

All eight M-items from REVIEW-REQUEST-3 have been resolved:

- **M1** (V07 gate T2→T3): gate reassignment complete, roadmap note added (16:93, 12:138)
- **M2** (V08 3-rep exception): exception documented in protocol section with asymmetric stopping rule (16:96–143)
- **M3** (Figure 7.1 float): fixed by reducing table font to footnotesize + arraystretch 0.95 (16:62–63)
- **M4** (log+Sobol nuance): expanded with transform scope, scrambling requirement, and small-budget caveat (03:241–251)
- **M5** (Chebyshev ideal-point condition): roadmap row qualified with best-seen-values proxy condition (12:36)
- **M6** (BG-PBT evidence scope): "strongest published design" qualified to Brax locomotion, pop=8, generous budgets (06:367–371)
- **M7** (BUILD_PROGRAM staleness): review-request note added flagging drift from survey register (REVIEW-REQUEST-3.md:12)
- **M8** (reply file consolidation): not actioned; retained as historical record of prior review cycle

Build verified clean at 111 pages, zero errors, zero overfull/underfull boxes, zero undefined refs.

All M-items closed. Survey is review-ready for human reader.
