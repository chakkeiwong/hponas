# Supported small tuning workloads

The master owner is WL-01. All maintained models run locally without importing
sibling projects or using their data. Finite correctness, packaging and empirical
generalization are separate claims. Accepted campaigns apply only to their
retained source; subsequent changes require integrated qualification.

| Workload | Configured model and objective | Fidelity and physical work | Evidence and limits |
|---|---|---|---|
| Numerical fitting | Rotated quadratic; learning rate controls finite-iteration error | 1–8 gradient updates, resumable | Exact rational spectral reference; Tier-1 finite source retained |
| Moderate architecture | Fixed-knot ReLU output fit; error and hidden width | One output fit; 128 architectures | Exact integrated error/Pareto reference; no arbitrary topology NAS |
| Population control | Finite stationary MDP, shared tanh policy/value network; expected return and distillation loss | Charged gradient updates, copied/reset momentum and durable generation state | Finite V08 accepted on archived source; no PPO or distributed scaling claim |
| Finance | Two-asset long-only allocation; variance and expected return | Projected gradient updates, 0–32; exact resume | Deterministic train/evaluation fixtures with mean (1,2), covariance diag(1,4); no real-market result |
| Hamiltonian fitting | Learned quadratic-feature Hamiltonian; derivative error and true-energy drift | One linear solve plus declared evaluations | Distinct initial states/times; complete basis recovers known oscillator; near-constant dynamics is an adverse control |
| Ordinary HMC | Gaussian leapfrog/Metropolis plus per-chain diagnostics | All warmup and retained gradients counted | Finite Gaussian V13 accepted on archived source; resonance and insufficient ESS retained; no broad SBC/calibration claim |
| Learned transport | Trainable one-neuron tanh coupling on known Gaussian pushforward | Nine-point autograd updates and transformed leapfrog gradient evaluations | Independent closed-form training and chain-rule reference; no posterior mixing/calibration or NUTS claim |

The finance template accepts `learning_rate` in (0,0.2), `return_preference` in
[0,12], and integer update fidelity in [0,32]. It reports both objectives,
train/evaluation moments, every actual iterate and incremental work. Its exact
scalar optimum is `x = clip((8 - return_preference)/10, 0, 1)`; the two-objective
efficient weights occupy [0,4/5]. Moment-matched evaluation rows differ from the
training rows. These exposed within-model fixtures are not empirical holdouts.
`examples/finance_tuning.py` executes the public vector Study/Store path with
fixed domain normalization and eight configurations (64 updates).

The learned transport is `T_b(z) = (z1, z2 + b*tanh(z1))`, an actual neural
coupling layer with explicit inverse and unit Jacobian determinant. The target
is the known pushforward with parameter `a`. Symmetric cubature gives training
curvature `C = 2*tanh(1)^2/3`, optimum `b=a`, and iterate
`b_n = a + (b_0-a)*(1-learning_rate*C)^n`. Automatic differentiation performs
the updates; an independent formula verifies them. The transformed target
energy and leapfrog use the learned layer and its Jacobian. This provides a
finite neural-transport training fixture, without asserting a calibrated MCMC
sampler. The legacy `workloads.sampler_neutra` callable remains ordinary HMC for
the funnel; its name does not change its algorithm identity.

The old broken Hamiltonian and sampler examples are retained under
`docs/program/evidence/2026-10-08/workload-disposition-01/legacy-examples/`.
Their maintained replacements use the explicit small models above. General
Hamiltonian neural-network training in `workloads.hamiltonian_mo` remains an
unaccepted prototype; it is not the restricted polynomial-feature template.

The examples make no acceptance decision. Independent raw verification is
retained in `docs/program/evidence/2026-10-08/workload-disposition-01/`.
Broader learned-transport calibration, application performance, finance customer
results and distributed service acceptance need separately specified evidence.
