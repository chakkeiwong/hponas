# Self-contained tuning problems with known answers

Date: 2026-10-05. Master revision: 1.90. Owner: `STAT-03P`.

The user requests simpler models inspired by the research projects, with no
dependencies on those projects. This supersedes the native-project integration
part of the revision-1.89 proposal. All fixture generators, objectives and
references belong in hponas and use its existing numerical dependencies.
There are no sibling-checkout imports, data downloads, external checkpoints,
services, or requirements to execute another project's program. The previous
FinMarketing diagnostic remains historical development evidence.

The central requirement is to know both the model solution and the optimum of
the specified *outer tuning objective*. Knowing a posterior or generating a
synthetic dataset does not automatically identify the best sampler setting or
regularization. Distinguish an analytic optimum, an optimum over a fully
enumerated finite domain, and a lower bound on what training could achieve.

## Four initial fixtures

### S1. Regularized prediction: Gaussian linear regression

Let `y = X beta + epsilon`, `X'X = n I`, independent
`beta_j ~ N(0, t_j)` and `epsilon ~ N(0, s I)`, with positive fixed variances.
Fit by minimizing `||y - X b||^2 + sum_j lambda_j b_j^2`. The factor n is
deliberately not absorbed into lambda. Under a standardized independent test
covariate with covariance I, expected excess prediction risk is

`R(lambda) = sum_j (t_j lambda_j^2 + n s)/(n + lambda_j)^2`.

The exact optimizer is `lambda_j* = s/t_j`, and the minimum is
`R* = sum_j s/(n + s/t_j)`. For each coordinate the exact excess risk is

`R_j(lambda) - R_j(lambda*) = n t_j (lambda-lambda*)^2 / ((n+lambda)^2 (n+lambda*))`.

This proves the global optimum for nonnegative penalties. A scalar penalty
with equal prior variances gives the familiar `lambda* = s/t`.

Initial fixture: n=8, d=3, t=(1/2, 2, 8), s=2, so the optimum is
`lambda* = (4, 1, 1/4)`. Search each penalty on [0.001, 100] in log coordinates.
The evaluator performs actual linear solves. Since squared error is quadratic
in the joint Gaussian variables, a symmetric second-moment cubature rule
computes this expectation exactly in real arithmetic with just 22 right-hand
sides. The reference uses the formula above independently.

This tests log scaling, regularization conventions, multiple continuous knobs,
and selection regret. The analytic answer concerns prior-averaged risk for
fixed penalties, not the optimum of an arbitrary realized validation sample.
An optional noisy mode can use independent Gaussian draws and evaluate every
selected configuration against the same exact risk afterward.

### S2. Numerical fitting: gradient descent on a quadratic

Let `f(w) = (w-w*)'H(w-w*)/2`, with a known positive definite H whose extreme
eigenvalues are m and L. Gradient descent has error update
`e_(k+1) = (I - eta H) e_k`. Define the tuning objective after T iterations as
the squared worst-direction error for unit initial error:

`J_T(eta) = ||(I - eta H)^T||_2^2 = max(|1-eta m|, |1-eta L|)^(2T)`.

Here the superscript T on the matrix denotes T iterations. Balancing the two
endpoints gives the global optimum `eta* = 2/(m+L)` and
`J_T* = ((L-m)/(L+m))^(2T)` for any positive integer T.

Initial fixture: eigenvalues (1, 3, 9), a fixed orthogonal rotation, w*=0,
eta in [0.001, 0.3], and T=4. The answer is eta*=0.2 and J*=0.8^8.
The evaluator executes the gradient updates on a basis of initial errors;
the reference uses the spectral expression. T in {1, 2, 4, 8} supplies genuine
fidelity levels with known curves. Eta above 2/L is an explicit unstable case.

This tests learning-rate tuning, cost/iteration accounting and multifidelity
plumbing. The objective is explicitly worst-direction error; the best eta for
one particular initial vector at finite T can differ. These curves alone do
not test schedulers on late-improving learners.

### S3. Time-series estimation: a constant-gain scalar filter

Let `x_t = x_(t-1) + w_t`, `y_t = x_t + v_t`, with independent noises of fixed
variances q>0 and r>0. Tune K in (0,1) in the update
`xhat_t = (1-K) xhat_(t-1) + K y_t`. Its stationary mean-square error is

`P(K) = ((1-K)^2 q + K^2 r)/(K(2-K))`.

The optimal posterior variance and gain are
`P* = (sqrt(q^2 + 4 q r)-q)/2`, `K* = (P*+q)/(P*+q+r)`.
For small q/r, compute P* by the equivalent stable expression
`2 q r/(sqrt(q^2+4 q r)+q)`. Global optimality follows from

`P(K)-P* = (P*+q+r)(K-K*)^2/[K(2-K)]`.

Initial fixture: q=1, r=6, giving P*=2 and K*=1/3; search K in [0.01,0.99].
The objective solves the error-covariance Lyapunov equation. Independent
short-path noise cubature verifies actual state/filter updates against the
finite-horizon covariance recursion. The stationary optimum does not claim to
minimize every finite-horizon error from an arbitrary initialization.

This tests a macro/filtering problem without importing a macro model. q and r
are fixed properties of the problem; changing them is not a tuning shortcut.

### S4. Architecture selection: a linear bottleneck network

Let the teacher be `y=A x`, with `E[x x']=I`, and fit a two-layer linear network
`yhat=W2 W1 x` with hidden width h. The expected prediction error is
`||W2 W1-A||_F^2`. Since the product has rank at most h, its global minimum is

`E_h* = sum_(j>h) sigma_j(A)^2`.

Truncated SVD attains the bound. The reference singular values are specified
when constructing A; they are not estimated by the same SVD being checked.
For an a-by-b teacher and no biases, parameter count is `p_h=h(a+b)`.
Thus both the complete error/size Pareto frontier and the optimum of the
declared objective `E_h* + c p_h` can be computed exactly for finite widths.

Initial fixture: a=b=4, singular values (4,2,1,1/2), h in {1,2,3,4}.
Errors are (5.25,1.25,0.25,0); parameter counts are (8,16,24,32).
With fixture cost coefficient c=1/16, scores are (5.75,2.25,1.75,2), so h*=3.
The full Pareto frontier is also retained: c defines one illustrative objective,
not an acceptance threshold or a claim about real compute time.

The evaluator constructs factor weights and recomputes prediction error and
actual array sizes. This tests integer architecture coordinates, complexity
accounting and multiobjective reference calculations. SVD isolates architecture
selection from training failure. In a later gradient-training variant, this
formula is an attainable lower bound; it is not automatically the optimum of
the finite-budget training experiment. Enumerate that small experiment if its
exact finite-domain tuning answer is needed.

## Additional scope without losing known answers

A later nonlinear fixture can use a one-dimensional ReLU spline with three
known, nonzero slope changes and an affine skip: its minimum exact hidden
width is three. Restrict hidden knots to a small declared grid and fit output
weights by least squares. Integrate squared error exactly interval by interval
and enumerate the finite architecture set. Do not claim a global solution for
arbitrary freely trained nonlinear networks from this restricted result.

A later sampler fixture can use exact Gaussian Hamiltonian flow with fresh
momentum: `z_new = cos(tau) z + sin(tau) p`. At tau=pi/2 the draws are
independent. The autocorrelation of a linear coordinate is cos(tau), and of
its centered square is cos(tau)^2. The maximum of their integrated
autocorrelation times is minimized at tau=pi/2 with value one, at fixed cost
per exact transition. Finite leapfrog/Metropolis tuning has a different
cost/error problem; use a separate small enumerated domain for that question.

## How the tests give objective answers

For every completed proposal retain config, objective, failure status and
cost. Compute simple regret against the known optimum and the entire
best-so-far regret curve. Record objective work separately from search overhead.
Do not require a stochastic searcher to find an exact real-valued optimum in
16 evaluations, or require every method to beat random search.

The deterministic layer needs no statistical superiority threshold. Correctness
means agreement with the independent mathematical reference within a justified
numerical envelope, valid search-space handling, correct best-result selection,
and correct accounting. Prototype floating-point checks use conservative
operation/conditioning-scaled engineering tolerances; they are not formal
interval-arithmetic certificates. Rational identities additionally check exact
regret for S1 and the rational S3 fixture without rounding. Scientific claims
remain limited to the actual equations and finite observations verified.

Use exact finite enumeration only for a finite domain. A dense grid does not
prove a continuous global optimum. If the reference is an interval [L,U],
report a regret interval [J-U,J-L] with evaluation error included, rather than
inventing an exact answer.

After the deterministic layer, exercise noise handling with draws from the
specified laws. Variants should change conditioning, noise level, signal
strength, scale, rotation and width tradeoffs by a fixed prospective rule.
Keep separate development and evaluation instances; no fixture should be
selected because a favored searcher wins. Report exact regret of the chosen
configurations even when search observations were noisy. Generalized claims
about randomized search performance still require independent replications
and an appropriate uncertainty analysis.

## Execution and master integration

`STAT-03P/STYLIZED-DESIGN` owns this self-contained specification.
`STAT-03P/STYLIZED-DIAGNOSTIC` owns the bounded proof-of-concept run: four
fixtures, four existing searchers, 16 proposals each, one fixed search seed,
one CPU thread, no GPU and a 180-second process cap. This is 256 objective
calls, with cheap local linear algebra. It measures feasibility; it is not
four new statistical acceptance campaigns. All failures and losses are kept.

The driver lives with development evidence until the specification is migrated
into maintained fixtures and independent tests. No diagnostic-only path may
serve as a release gate. `STAT-03P/WORKSPACE-PROTOCOL-MIGRATION` now means
integration of these local fixtures and explicit reconciliation of old
V04-T0/V05 and later protocol requirements. External-project adapters are
removed from that stage's scope. The historical native diagnostic and old PPO
contracts remain preserved; neither is a dependency needed to run the new suite.

This is a refinement within the master program, driven by the user's request
for self-contained models with known answers. The master remains incomplete;
the replacement release/protocol implementation remains internal work.

## Executed development prototype

The [self-contained driver](evidence/2026-10-05/stylized-validation-01/known_answer_diagnostic.py)
completed [50 numerical checks and 20 exact rational checks](evidence/2026-10-05/stylized-validation-01/run01/reference-checks.json)
in 0.00386 seconds. Four fixtures by four searchers by sixteen proposals gave
256 completed HPO trials. The [complete diagnostic](evidence/2026-10-05/stylized-validation-01/run01/summary.json)
took 15.691 seconds including HPO imports. The imported-module check found no
sibling-project source. These timings describe this small prototype on this
host, not a runtime guarantee for larger models.

The following are reference regrets of the selected configurations, evaluated
from the mathematical formulas. Rows have different units and are not averaged.

| Fixture | Random | Sobol | GP | TPE |
|---|---:|---:|---:|---:|
| Ridge | 0.0852913 | 0.0627293 | 0.0852913 | 0.0521173 |
| Quadratic | 0.0633780 | 0.00377039 | 0.0163403 | 0.00826503 |
| Filter | 0.0140125 | 0.00785470 | 0.000157327 | 0.00322725 |
| Bottleneck | 0 | 0 | 0.25 | 0 |

The bottleneck GP run evaluated widths 1 and 4, repeatedly proposed 4, and
never tried the optimum width 3. Its objective and selected-best accounting
agree with the reference; its search performance is worse than the known
optimum by 0.25. This is a retained finite-instance performance finding, not
a proof of a general ranking or a reason to change the fixture. Review finite
discrete search and duplicate proposals within the migration stage. A four-case
enumeration remains the appropriate exact baseline for this finite problem.
