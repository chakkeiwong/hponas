# Scoped exposure history and environment lineage

This is **STAT-03/D–F inside the existing master program**. It extends the
previous source scan with available Git history and explicit asset comparisons.
The evidence establishes scoped observations, not holdout eligibility.

`evidence/2026-09-29/stat-03/exposure-history-r2/review.json` binds the complete
declared scan. It covers **148 commits reachable from local refs/HEAD, 633 unique
selected text blobs, and 267 current files** under the declared code, workload,
test, validator, example and tool roots. Each commit has a raw tree-listing hash
and complete selected path/blob inventory. Each unique blob has its Git identity,
SHA256, byte count, all observed paths and matching line numbers. Reference tips
are checked for changes during collection. The scan took **6.18 seconds**.

The plan is written before scanning. Historical scope includes the declared
text suffixes and excludes archives, mutation copies and generated evidence;
symlinks are not followed. Current-file enumeration uses `rg --files --hidden`
and its standard ignore rules. No excluded directory, external repository,
unreachable object, deleted remote history or undocumented execution is
represented as covered. Literal aliases include common underscore, hyphen,
space and CamelCase spellings. Semantic renaming can still evade them.

No literal name match was found in this scope for HumanoidStandup, inverted
double pendulum, Pusher, Reacher, Swimmer or Walker2d. This establishes absence of
those matches in these bytes; it does not establish absence of task-specific
development exposure. The previously exposed Ant, HalfCheetah, Hopper, Humanoid,
inverted pendulum and diagnostic Fast retain their recorded exclusions.

Pinned source parsing also records imports, base classes and direct XML assets.
Exact XML element tag/attribute multisets give the following facts:

| Candidate / previously exposed environment | Candidate elements | Prior elements | Exact shared occurrences |
|---|---:|---:|---:|
| HumanoidStandup / Humanoid | 99 | 99 | 78 |
| Inverted double / single pendulum | 31 | 26 | 13 |

These counts neither prove nor disprove relevant algorithmic exposure. They
identify concrete shared structure for the capability-specific lineage contract;
there is no invented similarity cutoff. All candidate eligibility remains
unestablished, and no acceptance task or private selection seed is chosen.

The inference limit is identifiable without a human ruling: two histories can
produce the same local files and Git objects while differing in an undocumented
external tuning run. A verifier that sees only these inputs cannot distinguish
the two worlds. Consequently, local-byte checks cannot prove an unrestricted
non-exposure claim. The scientific design must state its evidence/trust scope
and obtain the missing records or explicitly justify a prospective design that
does not require that historical claim. Unknown inputs cannot be marked true.
Similarly, local hashes and Git timestamps do not establish externally anchored
freeze/reveal order or private-seed concealment.

`prepare_exposure_history.py` reproduces the scan into a fresh directory.
`exposure-history-r1` is retained as the source snapshot before the final
scheduler boundary repairs; `r2` records the current files. The program still
needs the operational exposure/chronology/isolation evidence contracts,
prospective rank sizing and measured resources. No human scientific acceptance,
PPO execution, GPU experiment or resource allocation occurred.
