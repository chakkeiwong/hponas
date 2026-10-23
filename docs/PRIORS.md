# Optional prior methods

`CategoricalPriorBandSearcher` couples the pinned NePS geometric/dynamic
portfolio to `PriorBandScheduler(default_at_target=True)` and `Study`. It
supports unconditional categorical products with at most 4,096 configurations.
The first default is evaluated at the highest fidelity. Bracket allocation uses
the reference's floor rule, fixed synchronous promotion quotas, stable
registration-order ties and no replacement of failed evaluations.

Each coordinate's default has 2, 4 or 6 times another category's probability for
low, medium or high confidence. Incumbent mutation changes each coordinate to a
uniformly selected other category with probability 1/2. The original 50-attempt
limit leaves a small, exactly retained probability of returning the incumbent.
Mixture weights use the bracket, observed losses and the reference's latest
completed fidelity accounting. Actual consumed work is recorded separately.

`FinitePriorSearcher` supports separately declared finite cells, including cells
in transformed or conditional spaces. Its law is
`(1-alpha) B + alpha w B / sum(w B)` with rational cell masses and weights.
It does not approximate a continuous density by sampling a few candidate points.

Both classes preserve the selected rejection branch across bounded calls.
`PriorPendingError` means the Study saved pending RNG and policy state; retry
`run()` or restore its checkpoint. Changing the proposal cap changes call
boundaries, not the completed draw law. Store recovery and event replay retain
trial, configuration, policy and scheduler identities.

```python
from hponas import (
    CategoricalPriorBandSearcher, Knob, LocalExecutor, PriorBandScheduler,
    PriorPendingError, SearchSpace, Study,
)
from workloads.streaming_quadratic import StreamingQuadratic

space = SearchSpace([Knob('eta_index', 'categorical', list(range(1, 26)))])
searcher = CategoricalPriorBandSearcher(
    space, {'eta_index': 18}, rungs=[1, 2, 4, 8], eta=2, seed=0,
)
study = Study(searcher, LocalExecutor(), StreamingQuadratic(), budget=21,
              legacy_reason='Exposed deterministic quadratic method fixture',
              maximize=False, continuation='resume',
              scheduler=PriorBandScheduler(rungs=[1, 2, 4, 8], eta=2,
                                           default_at_target=True))
while True:
    try:
        result = study.run()
        break
    except PriorPendingError:
        continue
```

`python -m examples.prior_tuning --output-dir /tmp/priors` retains good, wrong,
central and uniform-prior diagnostics, plus pending recovery and restart cases.
The workload executes actual quadratic gradient updates. Independent rational
reconstruction checks every trajectory, promotion and categorical mixture.
These finite engineering checks do not establish V11 superiority or recovery.

`ProductPriorBandSearcher` supports unconditional products of continuous,
integer and categorical coordinates, including log transforms for numerical
coordinates. It directly samples the reference's truncated Gaussian laws using
float64 inverse CDF. Integer draws use the original interval expansion by
0.499999 and rounding; their probabilities are CDF-bin integrals. Dynamic weights
use the original standardized Gaussian score on unexpanded integer bounds,
without adding a log-coordinate Jacobian to that score. The score is distinct
from the sampling density. The numerical recipe and library versions are bound
into checkpoints, and restoration reconstructs all proposals and observations.
No rejection fallback or finite candidate approximation is used for these laws.

`python -m examples.product_prior_tuning --output-dir /tmp/priors` retains six
numerical diagnostics. Integer tuning has a finite known optimum; continuous
tuning has a unique optimum obtained by differentiating the exact training loss.
Independent quadrature reconstructs every dynamic portfolio weight.

The original reference has no conditional-product or logit law. These two
searchers refuse those inputs explicitly; `FinitePriorSearcher` can sample
declared cells in such spaces under an explicit base measure. Arbitrary
continuous callable densities require a separately certified law. Floating
inverse CDF is a numerical implementation, not an exact-real arithmetic claim.

The earlier `PriorBand` class is a policy ledger. `PriorBandSampler` in
`hponas.searchers_priorband` and `PriorBandScheduler` in `hponas.schedulers` are
legacy prototypes. Their retained performance failures concern their original
implementations and fixtures; the new methods do not convert those outcomes
into passes. Installed-package qualification and prospective V11 acceptance
remain open, and priors remain opt-in.
