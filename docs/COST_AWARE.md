# Sequential cost-aware search

Use `hponas.CostAwareProposalSearcher` with `GPqLogEISearcher` from
`hponas.searchers_gp`. The new path combines CArBO's cheap-first initial-design
elimination and one-to-zero consumed-budget exponent with a censored log-cost
GP. It selects one point from a bounded global candidate pool. It implements
those policies on that pool; it does not claim a global optimum of the
continuous acquisition. Priors, batches, fidelity schedulers and noisy-objective
qualification are outside this method's verified envelope.

```python
from hponas import CostAwareProposalSearcher, Knob, LocalExecutor, SearchSpace, Study
from hponas.searchers_gp import GPqLogEISearcher

space = SearchSpace([Knob("learning_rate", "continuous", (.001, .1), transform="log")])
base = GPqLogEISearcher(space, seed=7)
searcher = CostAwareProposalSearcher(
    space, base, total_budget=100, initial_budget=12.5,
    cost_unit="declared_work_units", default_cost=8, seed=7,
)
# train returns {"value": loss, "cost": measured_work, "metadata": {...}}.
# Study(searcher, LocalExecutor(), train, budget=20, maximize=False).run()
```

The default pool has 16 candidates and a maximum of 256. Finite mixed spaces
up to the geometry's enumeration bound are sampled without replacement;
continuous spaces use bounded Latin-hypercube draws. The maintained GP base
supports unconditional continuous linear/log coordinates. The cost GP also
supports numeric, ordinal, categorical and conditional coordinates. A base
without explicit log-EI scoring requires `cost_only=True`; that mode is a
diagnostic, with no objective-improvement claim. Fitting and scoring failures
propagate and preserve the pending/accounting boundary.

For consumed evaluation work `spent`, the active exponent is
`clip((total_budget-spent)/(total_budget-initial_budget), 0, 1)`.
The score is `log(EI)-alpha*log(E[cost])`. During initialization, the policy
alternately removes the highest predicted cost and the closest candidate to
the previous design, using normalized numeric distance and categorical Hamming
distance. Ties retain a documented stable candidate order. Candidate generation
is an explicit bounded discretization, regenerated at each decision.

`total_budget` limits admission based on measured evaluation work, and a job
already admitted may overshoot it. It is not a hard interruption deadline.
Optimizer overhead is reported separately in the example and is not charged to
that evaluation-work budget. `Study.budget` remains a count of new trials.
Use `cost_unit="wall_seconds"` to model executor elapsed time; supply actual
physical work consistently when using `declared_work_units`. All observations,
including invalid results, retain their spent-work records.

The cost model fixes a Matérn-5/2 times Hamming kernel, unit signal variance,
lengthscale 0.5, observation log standard deviation 0.05 and jitter 1e-6.
`default_cost` fixes the prior predictive expected cost; the prior log mean
includes both the latent-variance and observation-noise correction. Completed
durations supply Gaussian log-duration densities. An externally enforced
deadline supplies survival likelihood only when its executor provenance is
present and `timeout_assumption="deadline_independent_given_config"` is
explicitly declared. This is a mathematical assumption, not an inference from
the word “timeout.” Objective-raised timeouts, quality stops, terminal failures
and interrupted aggregate accounting remain unmodeled. Local executor timing
distinguishes the objective call from a worker duration including startup.

Prediction uses Gaussian conditioning and exponential tilting of orthant
probabilities for the first two duration moments. It does not fit a Gaussian to
a censored posterior or mistake a lognormal median for expected cost. The
backend permits 128 modeled observations and at most 32 censors. A single
censor uses a stable normal survival function; two use scaled quadrature in
the declared numerical domain; larger censor sets use deterministic seeded
Genz lattice integration with a bounded sample schedule. Numerical error
estimates are not rigorous bounds. Unresolved integrals and unsupported
domains are refused before another evaluation. Exact moment identities do not
prove statistical calibration of this fixed model on arbitrary workloads.

JSON checkpoints bind the base model, cost model recipe and dependency
versions, observations, candidate traces, direction, pending proposal, RNG and
spent work. Recovery validates detached copies before replacing live state,
then cross-checks the Study ledger. No cross-version next-proposal identity is
claimed. Completed work is not repeated; a pending evaluation can be resumed by
Study's existing recovery policy.

Run `python -m examples.cost_tuning --output-dir /tmp/cost-example` for four
self-contained actual quadratic-training cases, including pending recovery,
direction reversal and measured-budget stopping. Independent rational training
and Gaussian cost reconstruction are in `validation.cost_reference`. The
example records physical gradient work separately from elapsed optimizer
overhead and does not establish optimizer superiority. Censor integration,
gradients, actual deadline provenance and invalid-work accounting have separate
conformance/integration checks.

The old `hponas.searchers_cost` module remains historical and has a reversed
trial-count schedule. Its prior evidence is not evidence for this repaired
method. Method qualification and the master program's cost acceptance design,
engineering requalification and Tier-1 scientific gate remain distinct.
