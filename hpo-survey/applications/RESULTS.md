# APP-01 five-family application validation results

These are independent stylized companions inspired by workspace contracts. They use no sibling imports, data, environments or services. Scientific source qualification remains separate from these bounded application results.

## Execution summary

| Family | Grid configurations | Guarded seconds | Grid seconds | Peak RSS MiB |
|---|---:|---:|---:|---:|
| forecast | 27 | 27.65 | 0.19 | 754.6 |
| wallet | 27 | 26.37 | 0.64 | 755.1 |
| policy | 24 | 25.87 | 0.28 | 754.4 |
| nas | 24 | 125.75 | 18.90 | 916.9 |
| transport | 24 | 92.59 | 12.33 | 869.7 |

60 scalar studies: five families, three fixed data replicates and four search methods, 16 proposals each. Every family also retains exhaustive reference fitting, fresh final fits and an interrupted/resumed random study. NAS adds three constrained vector studies and a separate promoted momentum-SGD recovery comparison. Reference work is additional; neither grid nor recovery cost is hidden in the search budget.

## Finite optimizer comparison

Losses have different units across families and must not be pooled. Tuning regret is best observed tuning loss minus the complete finite grid minimum with identical data and initializations. Final losses are protected evaluations of newly refitted models.

| Family | Method | Mean tuning regret | Exact finite minima / 3 | Mean final loss | Search seconds |
|---|---|---:|---:|---:|---:|
| forecast | random | 0.00310776 | 2 | 1.26623 | 2.81 |
| forecast | sobol | 0.00145838 | 0 | 1.26839 | 3.03 |
| forecast | gp | 0 | 3 | 1.26579 | 11.85 |
| forecast | tpe | 0.0179175 | 2 | 1.26807 | 3.11 |
| wallet | random | 0.00931603 | 1 | 1.20722 | 3.14 |
| wallet | sobol | 3.6363e-05 | 2 | 1.21208 | 3.00 |
| wallet | gp | 0 | 3 | 1.20967 | 10.62 |
| wallet | tpe | 0.00978098 | 0 | 1.25005 | 3.53 |
| policy | random | 0.0149155 | 2 | -0.380612 | 2.95 |
| policy | sobol | 0.0249526 | 2 | -0.424761 | 2.82 |
| policy | gp | 0 | 3 | -0.419212 | 10.26 |
| policy | tpe | 0.0149155 | 2 | -0.380612 | 3.25 |
| nas | random | 0.0025554 | 0 | 0.00891544 | 15.04 |
| nas | sobol | 5.29966e-05 | 2 | 0.002169 | 14.84 |
| nas | gp | 0 | 3 | 0.0108423 | 21.47 |
| nas | tpe | 0.00163083 | 2 | 0.0101262 | 15.41 |
| transport | random | 0.00272266 | 1 | 2.75049 | 10.88 |
| transport | sobol | 0.00287066 | 1 | 2.75142 | 10.81 |
| transport | gp | 0.000251187 | 2 | 2.75394 | 17.41 |
| transport | tpe | 0.00779443 | 0 | 2.74383 | 11.09 |

## Models and independent checks

### Forecasting
The latent process is AR(1), rho=0.6 and Q=0.15. The observed signal has known lagged exogenous and delayed auxiliary covariates plus latent state and Gaussian noise. Candidate lag, ridge and observation variance are statistical model choices. Regression uses observed training rows only; the filter conditions on observations only after their availability time. Selected fits refit on train+validation. An independently assembled joint Gaussian covariance gives the same conditional likelihood as recursive filtering; an augmented least-squares solve checks ridge coefficients. This fixture has sparse delayed observations, not a full macroeconomic mixed-frequency system.

### Censored wallets
Z=0.3+0.7x-0.2x^2+0.6 epsilon; W=max(exp(Z)-1,0). The zero mass is Phi(-mu/sigma); positive observations use a lognormal density with its Jacobian. Feature degree, ridge and fixed sigma form the finite domain. Scalar formulas, independent stationarity residuals and numerical quadrature verify likelihood and expected external wallet. The fixed-sigma coefficient problem is convex. Positive fitting regularization means the fitted optimum need not equal the generating parameters.

### Sequential policy selection
Three states, two actions, three periods and known logging probabilities form a controlled process. Threshold and time-slope policies are evaluated using a doubly robust estimator with train-only fitted transition/reward models and independent validation trajectories. Smoothing is an estimator hyperparameter. Independent enumeration of all state paths checks policy values. The unrestricted Markov optimum and best declared threshold class are separate references. Missing overlap and role leakage refuse explicitly. Final noisy estimates are not identified with exact policy values.

### Constrained NAS
Networks learn exp(-a*x) and both derivatives. Width, depth, activation and learning rate change actual trained models. Scalar comparisons use the sum of three validation MSEs. The vector workflow retains value-error/parameter-count fronts under separate maximum derivative constraints. Limits are frozen from an interpolation resolution h=0.25 and curvature bounds: h*0.6^2*exp(0.3) and h*0.5^2*exp(0.3). These are a declared numerical resolution target, not a universal financial materiality standard. Learned-model nonattainment is retained. The separate streaming test serializes weights and momentum through 40/120 updates and verifies interrupted trajectories against uninterrupted execution.

### Neural transport
The target is X1=Z1, X2=Z2+0.35(Z1^2-1), with iid Gaussian Z. Trained triangular maps T(z)=(z1,exp(s)*z2+MLP(z1)) have explicit inverse and Jacobian. Held-out model likelihood selects architecture; fresh final training precedes freezing. HMC uses the exact target pulled back through the frozen map. Every candidate gets development and fresh reversibility/volume/gradient checks; all passing pairs remain. Short retained chains have exact-target mean/second-moment discrepancies reported separately. A verified map or candidate is not a convergence certificate.


## Observed scientific outcomes

### Constrained feasibility

| Replicate | Feasible grid configurations / 24 | Tuning front | Feasible final fits | Terminal outcome |
|---|---:|---:|---:|---|
| 401 | 0 | 0 | 0 | no_feasible_full_fidelity_result |
| 502 | 0 | 0 | 0 | no_feasible_full_fidelity_result |
| 603 | 2 | 1 | 0 | final_evaluation_infeasible |

No constrained NAS result passes protected final evaluation. For replicates 401 and 502, the exhaustive declared grid itself has no feasible configuration under the frozen training budget. Replicate 603 has two feasible grid configurations and one search-front model, but its fresh final fit is infeasible. These are scientific nonattainment results, not execution failures. Enlarging training or changing architecture is a future program amendment, not an unreported relaxation of this test.

### Sampler verification and finite discrepancies

108 map/sampler pairs pass the finite numerical checks; 34560 transitions are independently replayed. Maximum absolute mean discrepancy is 1.35999 and maximum second-moment discrepancy is 1.39328. Short trajectories can therefore have substantial sampling error despite mechanically correct HMC. These diagnostics do not rank candidates or establish convergence.

### Accounting and scope

Total guarded family-operation time, including failed NAS attempts and recovery continuations: 298.23 seconds. This excludes separate controls, reconstruction, reporting and governance operations. Three data replicates provide descriptive comparisons only. The existing LaTeX manual is the accepted predecessor; this extension is documented by this report, README.md, the five-problem master and immutable evidence.

## Findings and limitations

The tables retain adverse and null findings. Finding a finite tuning optimum does not imply the best final score. Tiny numerical models can make complete enumeration faster than Bayesian optimization. Duplicate proposals are paid; deterministic repeats provide orchestration coverage rather than additional statistical precision. TPE retains its ten default startup trials and has only six potentially adaptive proposals. Ordinal encoding of categorical choices is explicit and may affect search behavior. Work units are documented proxies, not currency or hardware FLOPs. No production, real-bank, distributed-host or universal optimizer claim follows.

## Reproduction and authority

Use exact commands in docs/PROGRAM_OPERATIONS.md. Each command verifies the reviewed input manifest, preserves an immutable result directory, enforces CPU/time/RSS/disk/output bounds, and records source/runtime identity. Successful family allocations cannot rerun automatically. The live master and program.json own dependencies and status; the final APP-01 review precedes GAP-01/FINAL-AUDIT.
