# RL-LQR-08 boundary review and fixed joint allocation

The pilot was source-bound and consumed once: 73728transitions,17856SAC and
2048separate exact-Q diagnostic actor updates;76.61seconds. All three methods
share byte-identical initial actor parameters per seed. Plain outcomes remain
unfavorable; no source or pilot result is overwritten.

Both structured critics improved all three paired plain endpoints. The frozen
mean-final-regret selection rule chooses the model-informed adapter, subject to
the machine-readable REVIEW result. Its mathematical action-nullspace identity
and terminal Q hold by construction; this is fixture knowledge, not evidence that
generic SAC has learned these properties. Quadratic-only also helps, supporting
representation as an important mechanism but not isolating every interacting bias.

Add HANDOFF-ENGINEERING before HANDOFF: two bounded four-update transfer/adaptation
checks and donor immutability/actor freeze tests, at most16imitation/16critic-only
updates, zero environment transitions. This verifies new code before the six
scientific handoffs and does not consume those allocations.

Conditional JOINT uses seeds10821--10823,three members and three2048-step rounds.
At round0 a compatible GP learning-rate proposal replaces the worst only if
strict validation improvement. At round1 two GP/random mixed architecture/rate
proposals receive128distillation+128critic-only updates and1024transitions each.
Each competes with its recipient and immutable donor under the same paths.
Preserve every incumbent and best-ever artifact. The donor is not mutated.

Compare repaired BG-PBT, contemporaneous plain BG-PBT with the same safe scheduler,
and static random search using the repaired representation. All start from the
same three configurations (default plus two seeded draws) and actor seeds. Per
procedure20480transitions. Dynamic methods have4928SAC+256distillation+256critic-only
updates =20992gradient components; static has4928SAC+320extraSAC =20992components.
One SAC update counts actor+two critics+temperature (4); distillation counts actor+
two critics (3); critic-only counts2. Across9procedures184320transitions,45312SAC,
1536imitation,1536critic-only. Equality is in these work units, not wall time or
parameter FLOPs; both are recorded. Historical best remains validation-selected.

Validation seed1080001,4096paths; new test seed1089002,16384paths. Test evaluation
occurs only after writing immutable selection freezes for all three methods.
Three seeds give descriptive replication, not a5%distribution-free superiority
proof. Confirmation uses previously reserved10811--10813 and seed1089001 exactly.
Padded states and larger dimensions remain outside this allocation.
