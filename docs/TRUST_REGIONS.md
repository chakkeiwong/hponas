# Sequential mixed-space trust regions

`TrustRegionSearcher` fits an exact local Gaussian process and chooses a point
from a correlated posterior Thompson draw. Each region begins with a global
Latin-hypercube design (sampling without replacement for small finite spaces).
Only observations from that generation enter its GP. The complete Study ledger
retains observations and work across restarts.

```python
from hponas import Knob, SearchSpace, TrustRegionSearcher, LocalExecutor, Study

space = SearchSpace([Knob('rate', 'continuous', (.001, .1), transform='log')])
searcher = TrustRegionSearcher(space, seed=0)
study = Study(searcher, LocalExecutor(), objective, budget=30, maximize=False)
result = study.run()
```

The objective performs one complete training job and returns its scalar outcome
and actual work cost. A fixed-fidelity Study uses fidelity `1`; this denotes one
whole evaluation, not one training iteration. The maintained example
`python -m examples.trust_tuning` executes eight physical gradient updates per
configuration and retains every update and training checkpoint.

The continuous state machine follows TuRBO's strict raw-best update and separate
0.001 relative-improvement expansion test, success tolerance 3, failure tolerance
`max(4, dimension)`, initial length 0.8, minimum length 2^-7 and maximum 1.6.
Retirement occurs strictly below the minimum. A failed evaluation counts as a
failure without becoming a GP observation or a fictitious incumbent. If every
initial evaluation fails, the search starts another global design; if all finite
configurations fail, Study reports an incomplete result with the spent work.

The pinned original reference is
`uber-research/TuRBO@de0db39f481d9505bb3610b7b7aa0ebf7702e4a5`.
The maintained mathematical implementation is independent of the retained
reference source. The following extensions are explicit:

- Numeric and ordered integer coordinates use transformed unit coordinates and
  an anisotropic Matérn-5/2 kernel with a dimension-scaled lengthscale prior.
  Categories use an exponential Hamming kernel, with no ordering of labels.
  The two factors multiply. Conditional numeric features encode value and
  activation separately; inactive categories have a distinct label.
- Numeric region sides scale by lengthscales normalized to geometric mean one.
  The categorical radius is `min(d_cat, max(1, ceil(length*d_cat)))`.
  Newly activated numeric children use their declared global bounds. Only legal
  typed configurations are evaluated.
- A fresh exact GP fit uses median/population-standard-deviation normalization
  and 20 Adam iterations at learning rate 0.05 by default. A fitted nugget in
  `[1e-6, .1]` regularizes the deterministic observations. Thompson sampling
  includes that nugget, as in the pinned original predictive sampler.
- The bounded candidate pool defaults to 256 points. Continuous/large spaces
  use a Sobol perturbation block; small finite spaces enumerate legal neighbors.
  All already proposed configurations are excluded. A proven empty finite
  neighborhood causes a restart. A failed bounded search in a non-enumerated
  space raises an explicit error and rolls back its state.
- Every restart discards the previous region's training observations from the
  local GP and starts a new global design. Full finite exhaustion terminates
  Study with `reason='search_space_exhausted'`, preserving unused proposal budget
  and every result. This termination makes no quality or superiority claim.

The supported envelope is one pending trial, a noiseless scalar objective,
1–64 logical coordinates, at most 512 valid observations per region, and at most
512 candidates per posterior draw. Noisy objective declarations, concurrent
Study proposals and multifidelity schedulers are refused before work. A learned
nugget is numerical regularization; it does not implement noisy-incumbent or
batch trust-region semantics. Population-specific extensions remain in T2-POP;
scientific performance and default activation remain in V04-T1.

Recovery binds the space, method and runtime versions, objective direction,
proposal/configuration identities, controller journal, generations, trial/result
ledger, fitted parameters and RNG. A different constructor seed is allowed:
the saved seed and RNG replace it. Replay reconstructs candidates and posterior
choices from retained fitted parameters without refitting old models. Checksums
and cross-ledger consistency detect corruption; they do not authenticate a
checkpoint against an adversary who rewrites all its contents. Fits and draws
use CPU float64 with one Torch thread while preserving caller thread/RNG state.

`validation.trust_reference` independently conditions the scalar GP by NumPy
linear algebra and reconstructs its correlated sample, selection, controller
recurrence, actual training trajectories and work. The finite optimum follows
exact rational enumeration. The continuous eight-step loss is
`F(eta)=.01*(1-eta)^16+(1-3*eta)^16`, whose unique minimum on the declared interval
is `(1+r)/(3+r)` for `r=300^(-1/15)`. Regret is descriptive; these engineering
fixtures do not establish V04-T1 superiority.
