# Ten-state, multi-action SAC HPO/NAS companion

RL-LQR-05 is an additive known-answer experiment with ten physical states,
thirty decision steps and two, three, four or five continuous control inputs.
Input here means control input; the actor observation always has eleven values
(ten states plus remaining-time fraction).

## Action network and tuning
The SAC actor has an eleven-value input, two to four tanh hidden layers of
eight to sixty-four neurons each, and an output head of size 2m. The first m
outputs are Gaussian means and the remaining m are log standard deviations.
Stochastic SAC training samples then squashes with tanh; the exported action
network returns tanh(mean), an m-dimensional vector in [-1,1]^m.
The twin critics are independent networks taking 11+m inputs and each
returning one soft-Q value. Their architecture specification is shared;
their weights are independent. Actor and critic hidden layouts are selected
independently, together with separate continuous log-scaled learning rates
from 1e-5 to 1e-2.

Changing action dimension changes the environment/checkpoint contract; it is
not an architecture mutation. Cross-dimension replay, restoration and
distillation are refused. Architecture changes within a dimension use
training-replay actor/twin-critic distillation, then actual SAC training before
selection. No oracle action enters gradient training or transfer.

## Reproduction and interpretation
The source-bound operations and resources are listed in
../../docs/PROGRAM_OPERATIONS.md. Engineering precedes the once-only study,
independent reconstruction, rendered documentation and final master audit.
Do not rerun a consumed study allocation to recreate reports; reuse its
hash-bound checkpoints and results. A new experiment needs its own reviewed
allocation and source binding.

Each dimension has three paired optimizer seeds. BG-PBT and static search
share four initial configurations and seeds and equal total transition and
component-minibatch work. The default comparator is the best validation
checkpoint of the default static member, using only that member's work.
Thus the default comparison measures the gain from the larger tuning budget,
not an equal-total-compute optimizer comparison.

The exact feasible optimum is computed by Riccati recursion and verified by
independent condensed elimination and covariance propagation. Learned policy
expectations use 16,384 fresh held-out paths after all selections are frozen.
Read RESULTS.md for all numerical outcomes and selected training lineages.
Reported gaps and improvement fractions do not prove convergence, neural
optimality or general optimizer superiority. Results concern this fixed input
matrix family and rank-one process noise. The accepted core and predecessor
results remain unchanged.
