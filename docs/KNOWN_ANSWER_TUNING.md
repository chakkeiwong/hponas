# Self-contained tuning workloads

The maintained example `examples/known_answer_tuning.py` runs small numerical
models without sibling project source, data or services. Their independent
references are in `validation/tuning_reference.py` and the rational/analytic
tests in `tests/validation/test_tuning_extensions.py`.

| Model | Tuned coordinates | Observed objective and exact reference | Fidelity/work |
|---|---|---|---|
| Rotated quadratic training | 25 learning rates `i/40`, `i=1..25` | Squared error after eight matrix-gradient updates; exact spectral reference selects `9/20` | Iterations 1,2,4,8; resume uses 8 updates, repeated restarts use 15 |
| ReLU spline network | All 128 subsets of seven hidden knots; affine skip and fitted output weights | Integrated squared error and hidden width; exact polynomial integration gives minimum zero-error width 3 | One complete output fit; explicit fitted parameter count |
| Gaussian exact Hamiltonian flow | Correlation `cos(tau)` | Worst IACT of position and centered square; unique minimum 1 at `tau=pi/2` under constant transition cost | Nine cubature transitions per setting |
| Gaussian leapfrog HMC | Step size and trajectory length | Actual Metropolis transitions, per-marginal rank/folded R-hat and bulk/tail ESS; independent rational matrices and polar-integrated acceptance | Retained draws; all warmup/retained gradients counted, JSON resume preserves RNG and work |
| Quadratic-feature Hamiltonian | Basis terms and ridge regularization | Held-out derivative error and true-energy drift along the fitted dynamics; complete unregularized basis recovers the analytic oscillator | One numerical linear solve; fit/evaluation rows and matrix exponentials recorded |

The ReLU model fits actual hidden features and output weights. It has fixed knot
locations and does not represent arbitrary neural-network training. The
Hamiltonian model learns coefficients of quadratic features; it is a small
restricted network, with distinct training and evaluation initial conditions
and times. These within-model splits are not fresh statistical confirmation
data. Wider application claims retain their prospective protocols.

The sampler reports correctness before speed. Any divergence, R-hat above 1.01,
or bulk/tail ESS below 400 makes it ineligible for subsequent calibration.
Passing those vetoes alone supplies neither SBC nor reference-posterior
agreement. The short example intentionally retains its insufficient-ESS result.
The numerical Gaussian sampler implements ordinary HMC. The legacy
`sampler_neutra` callable implements ordinary HMC for the funnel and now reports
that exact identity, raw chains, warmup divergences and gradient work. Unsupported
targets are refused. Neither implementation supplies learned neural transport.

The adverse fixtures matter as much as the optima. An early-stopping scheduler
can remove the ultimately best learning rate. A sampler can accept every
proposal while its squared position never changes. A nearly constant learned
Hamiltonian can have tiny energy drift and poor predictive dynamics. Each is
checked objectively, without a human success judgment.

Run the bounded example with:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m examples.known_answer_tuning --output /tmp/tuning-observations.json
```

Run this command from the source checkout. Installed-wheel qualification for these models has passed on retained source;
changes require qualification again. The example never
changes the import path. The output file must be new; prior observations are never overwritten. These
models support the registered Tier-1 implementation and protocol-design stages.
They do not establish V06/V09/V10/V13 acceptance or general optimizer superiority.

Finance and actual learned tanh-coupling models are specified in [WORKLOADS.md](WORKLOADS.md), with independently reconstructed optima, training and recovery.
