# RL-LQR-07: why the scalar-state SAC experiment fails

The one-state/three-action case exposes inaccurate critic action rankings, biased learned feedback, and damaging architecture-transfer/replacement decisions. These are directly observed defects in the learned solution and weaknesses in our experimental design. No reward-sign, discount, terminal-mask, action-export, optimizer-rate or checkpoint-restoration defect was found in this trace. The causal origin of the critic errors is not fully identified.

## Exact diagnostic that applies to soft SAC critics

For b=ones(3)/sqrt(3), replace u by u_parallel=b.T*(b*u). The next-state distribution is identical, the box constraint remains feasible, and immediate cost falls by 0.1*||u_perp||^2. Consequently, for **any fixed future Markov policy**, including its future entropy terms, Q(x,u_parallel)-Q(x,u)=0.1*||u_perp||^2. The nullspace gradient must be -0.2*u_perp. We do not compare learned soft-Q directly with hard-optimal Riccati Q away from these policy-independent identities.

At the last decision, Q is the negative expected stage-plus-discounted-terminal cost; there is no future entropy bonus. This is a separate exact test.

## 1. The critics frequently prefer wasted effort

Each probe uses the current deterministic actor at 512 fixed replay observations. The table reports the minimum of the twin critics, as used by the actor. Counts diagnose these probes; they are not independent confidence samples.

| Seed | Wrong action ranking / 512 | Gradient points away from cheaper projection / 512 | Mean exact saved effort | Mean absolute Q-difference error | Terminal-Q grid RMSE |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10601 | 419 | 384 | 0.0005029 | 0.0047368 | 0.516601 |
| 10602 | 497 | 497 | 0.0005181 | 0.0080468 | 1.121103 |
| 10603 | 101 | 94 | 0.0049441 | 0.0100361 | 0.183452 |

The ranking errors remain 412, 489 and 101 when both the true improvement and contrary prediction exceed 1e-5, ruling out an explanation based only on float32 roundoff. Both individual critics also violate the identity. At stored behavior actions, the twin-minimum rankings are wrong in 185, 313 and 134 probes. This is not solely an issue of evaluating the actor away from previously sampled actions.

These are learned approximation errors, not proof of an incorrect RLlib gradient formula. The action-value error exceeds the small redundant-action penalty near the operating region. The scalar optimum has effective-direction curvature about1.1666 versus0.1 in each redundant direction: those directions require substantially finer discrimination. Terminal-Q errors are also present in the better scalar1 controls, so absolute Q error alone does not explain performance; action differences and gradients matter.

## 2. Biased feedback, rather than state size alone, explains much of the observed cost

We evaluate four frozen-policy transformations on4096 fixed diagnostic paths, seed1070001. Projection removes only wasted opposing effort. Odd symmetrization is pi_odd(x,t)=(pi(x,t)-pi(-x,t))/2. The joint transform applies both. Neither uses oracle action labels or changes network weights. This is post-hoc structural diagnosis, not fresh trained-method confirmation or a new search winner.

| Seed | Original cost | Projected cost | Odd-symmetric cost | Both | Original gap removed by both |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10601 | 0.309509 | 0.296416 | 0.293286 | 0.292935 | 72.55% |
| 10602 | 0.313085 | 0.298614 | 0.287077 | 0.287003 | 98.71% |
| 10603 | 0.962738 | 0.831329 | 0.368393 | 0.364471 | 88.49% |

The exact attainable optimum is0.286662585. Projection preserves the active state trajectory, and its cost reduction agrees with the previously computed nullspace gap. Odd symmetrization changes trajectories and is not guaranteed to improve an arbitrary nonlinear policy; it improves all three saved policies here.

The worst seed emits [0.1896,-0.0161,0.1889] at x=0,t=0 and [-0.1299,-0.5084,-0.1527] at x=0,t=29, where the optimal action is zero. Removing the asymmetry plus redundant effort reduces cost from0.962738 to0.364471, leaving a nontrivial residual. That isolates bias and coordination as major symptoms without proving their full training origin.

## 3. Architecture transfer is a destructive intervention in many saved trials

After64 transfer updates, scalar3 critic mean-square discrepancies from the teacher still range from13.67 to135.32. These are absolute value losses and must not be interpreted as gradient-fidelity guarantees. The transfer code immediately resets target critics to the imperfect online critics, resets SAC optimizer moments, then updates actor and critics together. There is no demonstrated critic-readiness or actor-gradient-preservation test.

In11/12 scalar3 architecture candidates, cost is worse after the following2048 SAC transitions than immediately after distillation. Across all diagnostic cases the count is34/36. For scalar3 seed10602, one candidate moves from0.347760 after transfer to496.405087 after SAC. For seed10603, another moves from0.758878 to1488.630720. The timing localizes the deterioration to post-transfer training, but the saved evidence cannot separate critic mismatch, actor rate, target reset and other interacting changes.

Crucially, all three selected scalar3 BG-PBT checkpoints have zero distillation updates in their lineage. Architecture transfer cannot explain away the underlying scalar3 SAC failures; it is an additional search weakness.

## 4. Population replacement has no incumbent comparison

The scheduler ranks four children, continues two, then installs both into fixed recipient slots without comparing them with those recipients. Three of six scalar3 replacements and10/18 across all cases replace a member with a worse measured child. A scalar3 seed10602 recipient at0.859618 is replaced by a child at14.931700.

Exploratory replacement is a possible design choice, not automatically a violation of BG-PBT. Here the finite budget gives those children little time to recover and no separate protected allocation for useful incumbents. An archived best checkpoint protects the final reported score, but does not recover the lost future population work. This rule must be evaluated as a repair, not silently changed in historical evidence.

## 5. Our tests and tuning design missed the relevant failure contracts

The prior27 tests establish dimensions, reference correctness, exact checkpoint continuation, accounting and transfer execution. They do not test whether critics rank equivalent controls correctly, whether gradients reduce real control cost, or whether transferred critics support safe actor updates. Engineering and reconstruction success were never a learning-convergence certificate.

The scalar3 winners receive1984--3008 SAC updates. The worst seed has actor rate1.7799e-5, entropy about+1.9 near zero versus the automatic target-3, and only9.85% of retained replay states within|x|<0.1, compared with44--46% in the other winners. This is consistent with incomplete actor adaptation and poor coverage of the relevant region. These observations do not establish that increasing training alone repairs the problem.

The search changes actor/critic architectures and rates while fixing update ratio(1 minibatch per4 transitions), alpha schedule, tau and transfer budget. It can therefore search a large configuration set without addressing the structural learning weakness. Positive entropy temperature alone is not a sufficient explanation: the exact redundant-action critic identity remains necessary, and a fully learned symmetric policy should not acquire these arbitrary directional biases.

## Checks that did not identify a plumbing defect

- Environment reward is negative quadratic cost; the final reward includes gamma times terminal cost so the discounted return has gamma^30 terminal weight. Terminal masking is correct.
- Replay rewards/dynamics agree with the formulas up to stored float32 observation rounding; clocks and done flags match horizon30.
- Restored learning rates and Adam counters match every saved task; target update clocks match the transition counts.
- Exported deterministic actors match tanh(mu) from the restored learner on the fixed grids.
- Upstream SAC uses reparameterized actor actions and separate critic, actor and alpha losses/optimizer parameter groups. Target updates are enabled at every learner call.
- No new training or original evidence mutation occurred in this diagnosis.

## Dependency-ordered repair program

1. **Make the scalar learner trustworthy before HPO/NAS.** Keep architecture fixed and add mathematical critic tests on redundant actions and last-step targets, actor-gradient direction checks, local symmetry diagnostics, and learning curves. Use a known quadratic/time-indexed critic as an independent diagnostic control to separate function approximation from actor optimization. A dynamics-aware critic or exact reward residual is an optional model-informed adapter, not a generic guarantee for bank problems.
2. **Isolate the training mechanism.** Prospectively compare one change at a time: critic representation/normalization and terminal handling, critic-only adaptation before actor updates, then actor/critic update ratio or rates. Treat entropy settings as a separate ablation. Reuse paired initial states and equal work; do not select fixes from exposed holdout results.
3. **Repair architecture handoff.** Validate actor behavior and critic action differences/gradients separately. Preserve a donor continuation and evaluate a bounded critic-adaptation period before releasing actor updates. Avoid treating an arbitrary fixed number of distillation steps as demonstrated transfer quality.
4. **Protect population incumbents.** Compare candidates to intended recipients under the same validation rule, retain best-ever policies and reserve explicit exploration slots if non-elitist replacements are desired. Verify this rule first on the saved18 replacement events.
5. **Only then rerun bounded joint tuning.** Freeze a prospective three-seed scalar3 comparison against the current source and matched static learner, with separate confirmation seeds and a reviewed resource manifest. Add padded states only after the simple learner diagnosis is resolved.

These repairs are ordered proposals, not completed learning fixes. This user request authorizes understanding the failure; the current master stage allocates zero training. A successor repair-comparison allocation must name its exact interventions, budgets and confirmation rule before any new learning.

## Evidence and scope

Diagnostic operation: docs/program/evidence/2026-10-28/rl-lqr-07/20261027T164854Z-diagnose-e084a525. Twelve saved checkpoints, no optimizer steps; 18.20seconds and approximately1.08GiB peak RSS. Counts are descriptive of the frozen runs. No general optimizer superiority, global NAS optimum, or completed learning repair is claimed.

