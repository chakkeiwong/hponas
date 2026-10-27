# HPO-NAS scientific checks 0.1.0

This optional distribution supplies finite scientific verification tools. It
installs as hponas-scientific-checks and imports as hponas_scientific_checks.
It does not require the hponas package, sibling projects, data services, Torch,
training or downloads at runtime. It does not add an optimizer or change the
accepted core wheel. Its qualification and source hashes are recorded separately
under SCI-03 in the consolidated master. Python >=3.12, NumPy 2.x and mpmath 1.3.x
are required. The concrete installed runtime is recorded in the delivery receipt;
a dependency range is not evidence for every possible version combination.

## Install and use

Install the retained wheel with pip install /path/to/hponas_scientific_checks-0.1.0-py3-none-any.whl.
Offline users must have its declared dependencies available locally. A reproducible
offline installation is exercised by the repository's fixed SCI-03 delivery operation.

Python API examples:

    from hponas_scientific_checks.nas_certificate import check_certificate
    result = check_certificate(model, paths, seconds=120)

    from hponas_scientific_checks.wallet import enclose, verify_partition
    bounds = enclose(selected_model, likelihood_model, max_leaves=2048, seconds=150)
    replay = verify_partition(selected_model, likelihood_model, bounds)

    from hponas_scientific_checks.pi_float32 import probability_of_improvement
    # logits and borders must be finite NumPy float32 arrays.
    probabilities = probability_of_improvement(logits, borders, incumbent_loss)

The JSON CLI is available through python -m hponas_scientific_checks or the
hponas-scientific-checks entry point. Commands accept one JSON input (at most
8 MiB) and optional --output NEW_FILE. Existing outputs are refused.

| Operation | JSON object fields | Meaning |
|---|---|---|
| nas | model, paths | Recompute fixed-domain derivative bounds |
| wallet | selected, likelihood | Enclose the five frozen-policy quantities |
| wallet-verify | selected, likelihood, report | Recompute every reported wallet cell |
| pi | logits, borders, incumbent_loss | Float32 finite BarDistribution PI |
| reference | points | Banana transform, inverse and exact density |

Example PI input: {"logits":[[0,0]],"borders":[0,0.5,1],"incumbent_loss":0.5}.
Its expected probability is 0.5. NAS model JSON uses config depth=2,width=4,
activation=silu and three affine layers (weight and bias arrays, 2-4-4-1).
Wallet models use config mean=intercept/linear/quadratic, scale=constant/linear,
incidence=censored/mixture and the matching finite theta vector in the retained
fitting bounds. Pass the inner model object when reading an APP-03 result wrapper.
Partition paths are binary strings from alternating coordinate splits.

## Interpretation and limitations

NAS CERTIFIED covers the real-valued saved network against exp(-x*a) on
[-1/2,1/2] x [1/5,3/5], with the original derivative limits. NOT_VERIFIED can
mean loose bounds or resource exhaustion; it is not a violating-point proof.
It says nothing about unseen seeds, training convergence or inference roundoff.

Wallet ENCLOSED means full-domain conservative bounds for the known synthetic
generator. Exact endpoint tuples are authoritative; display floats are approximate.
POSITIVE/NEGATIVE applies only if the entire paired interval excludes zero.
UNRESOLVED is a real outcome. Mathematical details and runtime assumptions are
in MATHEMATICS.md. This is conditional on frozen fitted policies, not a guarantee
of the tuning procedure across training seeds or real-bank effectiveness.

PI repair does not reverse the six failed saved ifBO comparisons. ifBO optimizer
integration remains cancelled. ifbo_reference.verify_case reconstructs the
finite saved histories with the repaired PI; it does not load pretrained models.

exact_references supplies banana_forward/inverse/log_density, harmonic_flow,
quarter_period_reference, half_width and required_n. Exact synthetic identities
do not prove finite-run convergence of arbitrary learned maps or leapfrog chains.
The uncertainty helpers assume frozen policies and independent observations.
Unknown MNAR and causal nonidentification need additional assumptions or data;
neither optimization nor these tools remove them.

Malformed inputs are refused. CLI return code 2 means an input/error refusal;
3 means NOT_VERIFIED; 0 means a computed result, which may be UNRESOLVED.
Never interpret exit code zero as empirical superiority.
