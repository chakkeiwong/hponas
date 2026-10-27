# APP-03 application repair guide

Current companion revision: 25 October 2026. The execution authority is
CONSOLIDATED_MASTER_AUTHORITY.md; docs/program/program.json records stage state.
The frozen repair plan is docs/program/APPLICATION_REPAIR_MASTER_2026_10_25.md.
Its prospective transport arithmetic amendment is
docs/program/evidence/2026-10-25/app-03/transport-plan-review-01.json:
200,240 transitions and 655,360 gradient evaluations are ceilings.

## What is delivered

These standalone synthetic examples exercise the public Study declaration,
finite search, budget accounting, tuning/final separation and artifact contracts.
They require no sibling project imports, data, environments or services.
They are companion workflows, not new built-in searcher defaults. The qualified
package source fingerprint remains
7a3975382cf19d55d3be3b653ccf5f860c576e13e7998a9dded47dff0a9adb17.

The current manual source is hpo-survey/main-app03.tex. It incorporates the
25 October repair chapter and retains the original product manual and survey.
The successful documentation receipt under evidence/2026-10-25/app-03 identifies
the built main-app03.pdf and all of its inputs. main.tex/main.pdf remain the
immutable 24 October predecessor. This guide does not assert completion of the
independent APP-03 audit or terminal GAP audit; consult the live master status.

## Models and tuning problems

| Family | Model and selection | Objective result and remaining limit |
|---|---|---|
| Wallet | Structural-zero/censored lognormal mixture, conditional mean/scale/incidence, 24 candidates. Fit once per training set; select expected capped-wallet utility less fee using observed validation outcomes. | 72 fits on three fresh datasets. Final utility differences versus likelihood selection: -0.0000151980, -0.0018289500, +0.0013524612. Mixed outcomes; no superiority claim. |
| NAS | Two-layer SiLU networks for exp(-x*a), widths 4/8, random-with-boundary or tensor training points, raw/normalized/polished loss. | 24 development fits choose width4/tensor/polish by feasibility, parameter count, worst ratio, then mean validation loss. Six fresh models pass both mesh and random checks; worst mesh ratio0.5753801. No continuous-domain/all-seed proof. |
| Transport | Frozen identity/exact/three learned triangular maps for a banana target; HMC length1 versus iid lengths8/12, step0.15. | Twenty map/policy/seed comparisons, four chains each,8192 gradients per chain including warmup. All retained, no posterior-driven ranking. Basic split-Rhat and batch-means ESS/MCSE are diagnostics, not convergence certificates. |
| Policy | Three-state, two-action, three-step logged MDP. Both policy threshold directions;48 configurations; two-fold cross-fitted tabular nuisance models. | 21 nuisance fits and291 evaluations. All three fresh selected policies equal the512-policy synthetic oracle. Known randomized logger and positive overlap required; no real-bank recommendation. |
| Forecast | Ridge covariate model with linear Gaussian latent state, lag1/2 and ridge0.01/1. | 27 fits; two rolling origins and one final fold per dataset. Independent Gaussian conditioning agrees. Information-time, gap, entity overlap and final-exposure refusals pass. Grouped refusal is separate from this temporal experiment. |

### Wallet identification and uncertainty

The validation utility is bounded conservatively by [-0.15,3]. For24 policies
fixed conditional on training and n independent MCAR validation observations,
the simultaneous two-sided radius is
3.15 * sqrt(log(48/alpha)/(2*n)). Report90/95/99 percent intervals, clipped to
the known bounds. No selected policy is certified better than zero at95 percent.
The same training-only policy is used in final scoring; there is no unreported
refit. These bounds do not apply to unbounded NLL, dependent observations or
adaptive retraining. They do not certify improvement over likelihood selection.

With observation probability0.75, observed capped-wallet mean1 and cap3,
the sharp unconditional mean interval is[0.75,1.5] without a missingness
assumption. Missing wallets equal to0 or3 generate identical observed data but
different total means. Optimization cannot identify which world generated data.
MCAR point identification is a simulation assumption, not a discovered fact.

### NAS training and evidence

Training uses81 points and480 Adam steps at learning rate0.03. Normalized
derivative weights are inverse squared inherited limits. Polishing uses
L-BFGS with at most80 iterations/100 objective evaluations. Limits remain
dx=0.12148729268184028 and da=0.0843661754735002.
Development uses seeds6401/6402 and a41x41 validation mesh. Recipe selection
precedes confirmation seeds7401--7406, an81x81 mesh and512 random points each.
One original attempt failed because tensor reload rounded weights to float32.
That failed source and receipt are retained. The v2 successor explicitly reloads
float64; it does not relax limits or reuse final data for selection.

### Policy and forecasting semantics

Policy nuisance fits are shared only for identical fold/smoothing inputs. Final
scores use independent trajectories after selection. The reported iid standard
error is a finite-sample diagnostic, not a guaranteed confidence interval.
Unknown identification or zero overlap causes refusal. The two causal worlds
Y(a)=a and Y(a)=U with A=U share observed Y=A but have ATE1 and ATE0.

Forecast folds train0:32/score34:48 and train0:48/score50:64; final uses
train0:72/score74:96 (Python end-exclusive notation). Two embargo outcomes are
masked while the latent state propagates. Predictions are one-step sequential:
an observation updates state only after it is scored. Final NLLs are
1.2568684,0.9817669,1.3772477. These are descriptive synthetic outcomes.

## Usage and reproducibility

Use public Study with a caller-owned Objective, StudyDeclaration and StudyBudget,
following the existing user guide. Source entry points are
hpo-survey/repairs/app03_wallet.py,app03_nas_repair_v2.py,
app03_nas_confirm.py,app03_transport.py,app03_policy.py,app03_forecast.py.
Their fixed finite enumeration adapter lives in common.py. Artifact records
retain physical configurations, folds, training IDs, score IDs and work.
The corresponding independently written app03_audit.py reconstructs retained
evidence without fitting or searching.

The exact operation forms are in docs/PROGRAM_OPERATIONS.md. For example:

    /home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py forecast
    /home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py documentation
    /home/ubuntu/workspace/hponas/program_operations/app_repair_v2.py audit

These are supervised, allocated operations, not unrestricted rerun commands.
Consumed operations refuse repetition. For a fresh experiment, prepare a new
versioned driver/manifest with declared data, objective, selection rule, finite
roster, independent reference and resource ceiling; register and review its
master stage before allocation. Never delete an intent or change consumed input
bytes to bypass this restriction. No sibling dependency or real-bank deployment
is implied. Read-only evidence inspection needs no scientific allocation:

    cat /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-25/app-03/20261025T054627Z-forecast-67ab7744/result.json

Receipts bind the complete output inventory and input hashes, including failed
attempts. Independent audit checks scores, rosters, selection, roles, work and
deliberately altered records. Administrative completion does not turn mixed
wallet results or MCMC diagnostics into scientific superiority or convergence.
