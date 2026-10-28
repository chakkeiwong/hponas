# RL-LQR-07: trace the scalar-state learning failures

## Scope and question
User authorization: pursue the simple case, trace the code, and understand what
we did wrong. This successor investigates the frozen RL-LQR-06 one-state,
three-action case, with scalar1 and padded3 checkpoints as diagnostic controls.
It does not rerun the study or silently change the accepted source.

## Reviewed sequence
1. TRACE: inspect environment/replay/terminal accounting, upstream SAC losses,
   target updates, actor export, architecture transfer and population selection.
2. DIAGNOSE: run bounded, zero-training tests against saved checkpoints. Check
   actor exports, recorded replay rewards and termination, optimizer rates and
   clocks, critic action differences/gradients, replay support and population
   replacement events. Use all three scalar3 selected policies, all three
   scalar1 controls and all three padded3 controls, plus the three scalar3
   default checkpoints. Summarize all saved learning and transfer curves.
3. REPORT: separate demonstrated mathematical violations, implementation/design
   defects, measured symptoms and untested causal hypotheses. State what would
   falsify each proposed explanation and order repairs by dependencies.
4. AUDIT: independently reconstruct reported arithmetic, source/artifact hashes,
   counters and diagnostic identities; final master reconciliation follows.

## Mathematical controls
For b=ones(m)/sqrt(m), project an action onto u_parallel=b.T*(b*u).
This preserves the next-state law and the box constraint. For any fixed future
Markov policy, including a soft SAC value with future entropy, the exact
reward-Q difference is Q(x,u_parallel)-Q(x,u)=0.1*||u-u_parallel||^2.
The nullspace projection of the exact action gradient is -0.2*u_perp.
These identities do not assume that the learned policy is optimal and do not
confuse soft-Q with the hard optimal Riccati Q. At t=29 the exact Q is simply
the expected terminal-transition reward, providing another policy-independent
test. Compare learned critics to these identities before attributing failures
to entropy or state dimension.

Frozen policy projection and odd-symmetry transformations are diagnostic
interventions only. They are not freshly trained models, confirmations or
new tuning winners. Previously exposed paths remain exploratory; new fixed
diagnostic paths are not an untouched performance-confirmation set.

## Bounds and evidence
No environment-training transitions, optimizer steps, distillation, GP refits,
new architecture search, GPUs or network in the operation. At most twelve
checkpoint loads, 512 deterministic replay probes per checkpoint, fixed
state/time/action grids, and 4096 evaluation paths per transformed scalar3
policy (seed1070001). One one-thread CPU process; 8GiB RSS; 1GiB output;
8GiB disk floor; 900seconds. An audit may replay evaluation, not training.
Hash all consumed sources/checkpoints and the published predecessor result;
preserve old evidence. Output identifies the source and exact probe choices.

## Review
This isolates critic contradictions and transfer/selection mistakes cheaply.
It cannot prove that a proposed repair restores learning, infer population
effectiveness from three seeds, or attribute all error to one cause. Entropy
regularization is a hypothesis, not an explanation established by its presence.
Do not demand agreement of learned soft-Q values with hard optimal-Q values
away from the exact identities above. No human success threshold.
New training, if warranted by the findings, needs its own prospective bounded
repair-and-comparison stage and is outside this diagnostic allocation.
