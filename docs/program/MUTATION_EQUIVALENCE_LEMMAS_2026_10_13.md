# Source-bound mutation equivalence lemmas

These are conditional semantic proofs, not human acceptance or tests standing
in for a proof. Only exact generated functions satisfying the executable
checker may be excluded, and only after they actually survive. All generated
mutants remain recorded. The existing five-percent allowance still applies.
Unknown transformations remain in the denominator and critical-path veto.

The two modern-GP additions below were reviewed on October 3, 2026
(Asia/Shanghai) while attempt 07 remained frozen. They apply only prospectively.

The observation domain is the documented behavior of the named implementations:
values, exceptions on supported inputs, state transitions and externally visible
side effects. It excludes source/bytecode/docstring inspection, monkeypatching
builtins or implementations, corrupted private state, resource exhaustion and
allocation timing. The GP lemma below applies only to valid public-API states.
These assumptions are explicit limits, not a proof of arbitrary Python program
equivalence. Test failures remain failures even when outside a lemma's domain.

1. **builtin_nan_case_v1.** Python's built-in float string grammar treats the
   spelling of NaN case-insensitively. Replacing only that case in a direct
   `float` call preserves the resulting float type, NaN status and represented
   bits on the pinned interpreter. The checker refuses modules that bind or
   shadow `float`, checks the represented bytes, and requires the remaining
   normalized function AST to be identical. NaN's lack of reflexive equality
   does not distinguish the programs: both executions produce NaN, and all
   allowed consumers see the same representation and operations.

2. **full_population_slice_v1.** In the three named bootstrap promotion
   functions, the branch sets n_pop=len(pop). The ASHA/Budgeted sorted list has
   exactly len(pop) entries. The MO ranking contains at most len(pop) indices:
   the dominance graph has one vertex per input row; the strict Pareto relation
   has no directed cycle, and removing each edge can make its target's incoming
   count zero only once. Thus each vertex enters a front at most once. Sorting
   and zipping a front do not add indices. A slice ending at n_pop and an
   open-ended slice therefore select every item in each case. The bound is read
   only by that slice. The checker binds the entire reviewed scheduler source
   hash, verifies that single use and permits only `n_promote=n_pop` to become
   `n_promote=None`. Changes to the ranking implementation invalidate the proof.

3. **unused_gp_stack_v1.** For a valid GPqLogEISearcher state, `_model` can be
   non-None in the public proposal path only after `_build_gp` stacked the
   nonempty observation list. Constructor, observe and checkpoint load set
   `_model=None`; proposal rebuilds it. Observe stores ordinary float64 vectors
   of the fixed dimension; recovery validates shape, finite values and counts
   and constructs fresh tensors. No public step between `_build_gp` and
   `_build_acqf` changes these inputs. Repeating `torch.stack(self._X)` therefore
   succeeds without mutating the vectors, consuming RNG or affecting model
   state. The local X_train is never read in `_build_acqf`. Replacing only that
   assignment's RHS with None preserves every observation in the stated domain.
   The checker binds the entire reviewed GP source and verifies the exact
   assignment and absence of any load of that local variable. Malformed private
   states and allocation failures are outside this lemma, explicitly.

4. **tpe_replay_copy_v1.** This lemma concerns the concrete TPESearcher restoring
   ordinary, finite JSON checkpoint values, as used by the persisted public
   Study contract. It excludes custom Python copy/equality hooks, subclass
   overrides and concurrent edits to the supplied checkpoint. It does not
   assert equivalence for arbitrary Python object graphs. These restrictions
   follow the serialized-checkpoint domain, not the observed test outcomes.

   In the bound `load_state_dict`, the input ledger is read only. A deep copy and
   a shallow list copy expose the same ordered JSON values. Induct on the
   processed event prefix. Both executions construct the same fresh sampler
   from the same seed. For a proposal event they use only the length and value
   equality of its configurations; `propose` generates and retains fresh
   configurations in both executions. For an observation event, both executions
   select the same pending trial by configuration value, tell the same scalar
   to Optuna, and `observe` deep-copies the input result before retaining it.
   Neither branch mutates or retains an input ledger container. The induction
   therefore preserves sampler calls, optimizer state, owned event values and
   every later proposal. A rejected event raises at the same branch before the
   final live-state update. JSON copy operations introduce no user-defined side
   effects; resource exhaustion is outside the common domain stated above.

   Consequently changing only `copy.deepcopy(state["events"])` to
   `copy.copy(state["events"])` in that replay loop is equivalent on this domain.
   The whole TPE source is pinned, including `propose`, `observe` and retention
   behavior. Shallow-copying `state_dict` or `observe` is not covered: those
   changes can expose live optimizer state to callers. Their concrete ownership
   counterexamples remain tests. This fourth rule applies only to a later
   prospective freeze; attempt 06 retains its unproved critical survivor.

The former `max(1, ceil(n/eta))` candidate is **not** one of these lemmas. Actual
floating division supplied a counterexample. Production now uses exact rational
integer arithmetic and has boundary checks against a Fraction oracle.

## Prospective protocol 2.7 extension

The following exact rules apply only to a new execution frozen after attempt
07's evidence is retained. They do not reclassify that campaign. The concrete
source, companion-source and runtime bindings live in `validation/v03_equivalence.py`.
Changes invalidate the rule until reviewed prospectively. The common domain
also excludes subclass overrides, custom copy/comparison/tensor-dispatch hooks,
concurrent edits and inspection of private attributes. Ordinary finite JSON
checkpoints and ordinary Python scalar values remain included.

5. **gp_invalidated_cache_v1.** The concrete constructor, successful observe
   and successful recovery invalidate `_model` and `_acqf`. Changing exactly
   one final invalidation from None to the empty string preserves a relation
   equating public state, with either sentinel in that slot. Refusals occur
   before the changed assignment. Serialization and capabilities do not read
   these caches. Zero-sized and Sobol bootstrap proposals do not read them;
   positive fitted proposals unconditionally build the same model from the
   nonempty validated observation lists before `_build_acqf` reads `_model`,
   then build the same acquisition before optimization reads `_acqf`. A build
   failure occurs at the same operation, and retries repeat those assignments.
   Induction over public calls preserves values, exceptions, RNG and side
   effects. Private helper calls and priors inspecting private caches are
   excluded. Other sentinels or assignments are not covered.

6. **pasha_empty_interval_v1.** Changing `_update_epsilon`'s guard from
   `comparison_top <= 0` to `< 0` differs only at zero. The subsequent lower
   and upper bounds are respectively `rungs[-1]` and `rungs[0]`. Increasing
   rungs give lower >= upper, so no resource satisfies lower < r <= upper.
   Every pair continues with latest=None, no distance is added and epsilon
   remains unchanged. Ordinary string IDs and finite numeric dictionaries
   introduce no comparison side effects. Extra finite work is outside the
   observation domain. Negative and positive comparison tops behave identically.

7. **pasha_falsey_report_default_v1.** In the bound report method, replacing
   the absent-key default `{}` with None, or omitting it, changes only the
   value of a local truth test. Both defaults are false and neither escapes.
   A present key yields exactly the same dictionary. Parent reporting and
   subsequent setdefault operations are unchanged.

8. **pasha_reversal_flag_v1.** The local `reversed_once` flag is initialized
   to False, then only assigned True or tested for truth. None has the same
   initial truth value. Each resource iteration therefore takes the same
   branch and either preserves the relation or sets both flags True. Distances,
   stopping point and epsilon agree. No flag type or identity is observed.

9. **pasha_latest_comparison_v1.** Shared resource keys are unique and sorted
   descending. Replacing `r < latest` with `r <= latest` adds exactly latest
   as the first iteration. Its ordering repeats the identical finite comparison
   used to establish the current ordering; the reversal flag is still false.
   Neither branch changes state. All later iterations have the same inputs
   and state. Strict value-order changes are not covered: retained tie cases
   distinguish them. Likewise promotion `continue` to `break` is not covered:
   public recovery can restore a sparse upper rung and an eligible lower rung.

10. **cmaes_scalar_config_copy_v1.** The concrete CMA-ES constructor admits
    nonempty unconditional continuous spaces with ordinary string names.
    The separately bound SpaceEncoder decoder produces a fresh string-to-float
    dictionary and the bound Config adds no nested objects. Each shallow or
    deep copy therefore creates a distinct dictionary with the same immutable
    contents. The returned, pending and ledger mappings retain the same ownership
    separation. Edits to a returned Config cannot change the other dictionaries.
    Sampler calls, matching, later recovery, exceptions and RNG agree. Only one
    exact `copy.deepcopy(config.values)` call in suggest may become copy.copy;
    nested checkpoint/state copying is not covered.

11. **local_falsey_guard_v1.** The named local initializers are evaluate_trial's
    `streamed=False`, GP observe's TypeError fallback `finite=False`, and GP
    control validation's fallback `valid_beta=False`. None either reaches the
    same immediate false-value refusal or is overwritten by the same Boolean
    before use. If evaluation fails before overwriting streamed, subsequent
    metadata handling uses only its truth value. None preserves those branches;
    the local value never escapes. True is distinguishable and is not covered.

12. **gp_library_default_v1.** On the fixed import bindings and pinned versions,
    MaternKernel's nu default is 2.5 and Sobol's scramble default is True. The
    checker also verifies the actual callable signatures. Omitting exactly
    those keywords supplies the identical argument value while leaving all
    other argument evaluations unchanged. Other defaults are not covered.

13. **gp_tensor_construction_v1.** Valid observations and restored Y values
    are scalar float64 tensors, so their stack has shape (n,). Inserting at
    -1 or +1 produces the identical (n,1) view. In bootstrap proposals the
    pinned SciPy Sobol output is a float64 NumPy array; tensor construction
    without dtype or with dtype=None infers that same row dtype. Finally,
    fitted bounds stack zero and one vectors. Changing the dtype of exactly
    one vector to a supported default floating dtype still represents zero
    and one exactly, and stacking with the unchanged float64 vector promotes
    to float64. The resulting bounds values, shape and dtype are identical.
    The CPU domain supports float16, bfloat16, float32 and float64 defaults;
    the checker rejects others. Torch 2.13.0, SciPy 1.18.1 and NumPy 2.5.2 are
    bound; the library-default rule also binds GPyTorch 1.15.2. Changing both
    vectors, arbitrary dtype/device dispatch or another constructor is excluded.

14. **gp_unused_batch_argument_v1.** The concrete `_build_acqf` never loads
    its batch_size argument, forwards it, or exposes its frame. Changing its
    caller's ordinary integer n to None changes no executed operation or
    state in that method. The checker confirms the absence of loads and the
    exact single call rewrite. Optimizer `q=n` remains intact. The separate
    `fork_rng(devices=[])` to None change is not equivalent: it can initialize
    unavailable accelerator RNG state and has a public CPU-only counterexample.

15. **tpe_unused_bookkeeping_v1.** In the entire bound concrete TPE class,
    `_n_proposed` and `_n_observed` are only initialized and updated by ordinary
    integer arithmetic. No public return, checkpoint, Optuna call, condition or
    exception message reads either value; the checker confirms no attribute
    load anywhere in the module. `_next_trial_id` is never read or updated at
    all. On ordinary integer proposal counts, changing a counter initialization
    0 to 1, +=n to =n or -=n, or +=1 to =1, -=1 or +=2 preserves all public
    observations. Changing the never-read next-trial initializer to None or 1
    also does so. The relation allows those private fields to differ and equates
    everything else; induction over calls preserves it. Recovery's dictionary
    update only installs another such related state. Custom numeric hooks,
    private-state inspection, subclass overrides and resource exhaustion are
    excluded. A None initializer for either arithmetic counter is not covered,
    because a subsequent update can raise. No other counter/value change is
    accepted, and the actual proposal/observation ledger remains unchanged.

16. **replay_unused_batch_default_v1.** `ReplayEngine.verify_determinism`
    replays the recorded event order and does not load its batch_size argument.
    Changing only the ordinary integer default from 1 to 2 therefore leaves
    every executed operation unchanged. The checker pins the entire replay
    module, verifies absence of loads and the exact single default change.
    Signature/frame inspection is outside the common observation domain.
    The distinct `record_optimization_run` function does use batch_size and
    receives no such exemption.

17. **replay_empty_promotion_queue_v1.** The initial promotion queue is tested
    only for truth until a promotion round or implicit promotion replaces it
    with `list(scheduler.promote())`. Replacing exactly the initial empty list
    with None preserves that false truth value. A queue pop is guarded by its
    truth value, and the list comparison in an explicit round follows the
    replacement by list(). Thus neither version can pop or iterate the initial
    false value. Once replaced, both queues contain the same owned list and
    their operations agree. Induction over the event sequence preserves all
    public observations, including the final nonempty-queue refusal. Initial
    allocation and frame/private-state inspection are outside the common domain.
    The checker binds the entire replay source and the one exact assignment;
    other queue values or later operations are not covered.

Each certificate binds the module bytes, actual generated module bytes and the
original/mutated function spans. The verifier reconstructs the named functions,
compares the generated original with live source and re-applies the exact lemma.
The permitted rules and this argument are frozen before execution. No reviewer
name, descriptive approval or aggregate score can create an exclusion.

18. **modern_gp_kernel_flag_v1.** In the exact concrete GPSearcher fitted
    proposal, replace only the covariance factory's `use_rbf_kernel=False`
    argument with None. The pinned BoTorch factory reads that argument once,
    only in `RBFKernel if use_rbf_kernel else MaternKernel`; it neither stores
    nor forwards the flag. Both values are false, so every constructor, prior,
    parameter, RNG action and later observation is identical. The verifier
    binds the full GPSearcher source, the installed BoTorch/GPyTorch/Torch
    versions and the exact reviewed factory source hash. Changes elsewhere,
    flag omission (whose default is True), custom factories or monkeypatching
    are not covered.

19. **modern_gp_training_axis_v1.** Replace only `X_train.shape[-1]` with
    `X_train.shape[+1]` in the concrete GPSearcher fitted proposal. On the
    supported scalar Knob/Parameter domain, each accepted configuration is
    encoded as a one-dimensional NumPy vector of the nonempty space's fixed
    length d, then converted to a one-dimensional tensor. Training assembly
    stacks a nonempty list of these vectors, giving rank two and shape (n,d).
    Missing mappings are skipped; empty assembly refuses before the changed
    expression. Invalid encodings or inconsistent shapes likewise refuse
    before it. Both indices therefore return the same ordinary integer d.
    The following covariance factory and every later operation receive equal
    inputs. The checker binds the full searcher plus encoding, space and type
    sources and the Torch/NumPy versions. Tensor subclasses, helper overrides,
    concurrent mutation and corrupted non-scalar states are outside the common
    domain; no change to another axis or another expression is permitted.

20. **ray_terminal_retry_bound_v1.** In the bound concrete RayExecutor
    streaming method, replace only `range(self.max_retries + 1)` with
    `range(self.max_retries + 2)`. Construction validates max_retries as a
    nonnegative ordinary integer m. Both ranges enumerate identical indices
    0 through m. At each index, successful collection returns; a non-Ray
    exception propagates; the polling loop cannot fall through (it is an
    unconditional while with no break). A Ray exception leaves the poll via
    the handler, which returns unconditionally when attempt==m. Cleanup may
    finish, raise, or wait without returning, but contains no break/continue
    that could suppress that terminal return and advance the for loop. Thus
    reaching index m+1 is impossible in both terminating and nonterminating
    executions. Identical prefixes preserve requests, retries, reports, costs,
    cleanup and outcomes. The checker binds the complete RayExecutor source
    and requires exactly this one range-expression change in this one method.
    Concurrent edits, arbitrary reassignment of max_retries and range/source
    introspection are outside the common validated public-state domain.


# Prospective review of the three changed equivalence contexts

The actual workspace freeze failed before calibration or mutation execution.
Its source guard correctly detected later-phase edits to executors/base.py,
replay.py and searchers_gp.py. The exact differences from the accepted mutation
workspace are retained in proof-context-differences.patch. The 352 preceding
tests checked historical proof fixtures; they were not proof of current-source
readiness. Preserve that distinction and the failed preflight.

No equivalence rule is added. For the existing rules, the changed contexts have
the following semantic argument on the same documented observation domain:

- evaluate_trial now always emits execution metadata. Its only newly moved
  read of `streamed` selects the mode with a truth test; False and None select
  the same endpoint branch. On success, signature inspection overwrites both
  initial values with the same Boolean. On earlier failure, only their truth
  values are read. The flag itself is never returned or stored. The added
  accounting and duration-scope literals are independent of the flag. The
  existing local_falsey_guard_v1 relation therefore still preserves values,
  failures and metadata, excluding timing exactly as before.
- Replay adds explicit exhaustion/pending events and method/scheduler trial
  registration. None of the new statements reads batch_size or promotion_queue.
  The argument batch_size is still never loaded. Until the initial queue is
  replaced by list(scheduler.promote()), its uses remain truth tests and a
  guarded pop. New event calls cannot access that local queue. The same
  induction over the event prefix proves replay_unused_batch_default_v1 and
  replay_empty_promotion_queue_v1. The new Config identity and exception handling
  occur identically in both executions.
- GP adds log_expected_improvement and validate_observations. Every previous
  method's normalized AST is unchanged. The finite scoring method uses the same
  nonempty observation check, then unconditionally rebuilds the model and
  acquisition, in that order, before reading acquisition values. It does not
  modify observation tensors. The validation method only reads those tensors
  and their count. Thus the existing unused-stack, invalidated-cache, tensor,
  library-default, unused-batch-argument and local-flag proofs extend to these
  new public call paths. In particular, empty-history scoring returns before
  reading either cache, and positive-history scoring overwrites both caches.

Update only the three reviewed full-file hashes and their independent source
fixtures. Rebase the three changed function specimens onto the new function
bodies, preserving their exact single transformation; these are constructed
proof-checker controls, not new observed mutant outcomes. Preserve all original
specimens in the archive. Actual final exclusions still require a surviving
generated mutant, exact full function comparison and the same bound semantic
rule. Add no new exclusions or numerical allowance.

Retain the original proof document unchanged. A new argument document appends
this context review and is bound prospectively by V03 2.9. Repeat the affected
proof/harness checks and the actual isolated-workspace preflight on the repaired
source before any scientific allocation.


# Prospective product-source context review, 13 October 2026

The preceding 8 October argument is retained verbatim. Its historical bindings
remain historical. Before any final product campaign, the four changed source
contexts have been reviewed against their archived independent source fixtures.
The exact changes and AST comparisons are retained under
docs/program/evidence/2026-10-13/bank-integrated-review-01/.

Legacy GP and TPE add a typed support property and route the public capabilities
report through it. CMA-ES adds the same class-level support object and report.
All other method ASTs are identical. These support declarations only construct
literal capability values and return a detached dataclass report. They neither
read nor write optimizer caches, observation tensors, private counters or
configuration mappings. Existing copy, unused-state, cache, tensor, flag and
library-default relations therefore extend to the added public calls. The
capabilities source is separately bound in the context review. Any future
change requires renewed exact-source review before qualification.

Modern GP moves fitted construction into _suggest_joint_impl(count), used by
both single and joint proposals. The whole SingleTaskGP covariance-construction
AST and the data-assembly/encoding methods are unchanged. In every branch that
reaches that construction, training X has shape (n,d) under the existing domain;
-1 and +1 therefore return the same integer d. The BoTorch factory still reads
the False/None flag only as a truth test. The same pinned versions and factory
source hash are required. Thus either exact single rewrite constructs identical
models and preserves RNG state. Pending points, joint enumeration/optimization,
checks and retained proposal batches subsequently receive identical inputs and
execute identically. Neither rule exempts new batch/pending or acquisition
logic. Other axis changes, flag omission and multiple changes remain refused.

The two modern-GP verifier specimens are rebased to this exact method body with
the same explicit transformations. Their names are constructed test identities,
not measured mutants. All other specimens remain unchanged. Every actual
certificate still binds generated module bytes, exact function spans, current
source and its runtime/dependency domain. No equivalence rule or threshold is
added or relaxed and no historical outcome is reclassified.

The original critical list is retained. The moved joint implementation, finite
joint maximizer, batch entry and pending-location derivation are additionally
critical so the refactor cannot evade the zero-unproved-critical-survivor rule.
