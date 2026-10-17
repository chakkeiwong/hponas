# Optional GP robustness

`RobustGPSearcher` uses learned monotone Kumaraswamy input warps, a fitted
Yeo-Johnson output power and a noisy acquisition ensemble. It implements a
bounded subset of the mechanisms discussed in the survey's GP robustness
section. Full HEBO parity and empirical improvement are not established.

Use `RobustGPSearcher(space, seed=0, maximize=False)` with a `Study` using the
same direction. The default `GPSearcher` is unchanged. Run
`python -m examples.robust_gp_tuning` for seven actual training evaluations
whose gradient updates have an exact spectral reference.

Supported spaces have 1–16 unconditional continuous axes, with the native
linear/log/logit transforms. The GP adds a learned input warp on normalized
coordinates. Observation powers are fitted in [-2,2] by Yeo-Johnson likelihood
after median/MAD scaling; constant data uses the identity. This preserves
ordering but changes distances and uncertainty units. The GP estimates one
observation-noise variance in transformed output space. This does not constitute
a calibrated heteroscedastic likelihood on the original objective scale.

The model scores a seeded Sobol candidate set using joint latent-posterior
samples. Expected improvement and improvement probability integrate over the
uncertain incumbent; the third criterion is posterior mean plus twice its
latent standard deviation. It selects uniformly among nondominated candidates
with the searcher's recorded generator. These are bounded Monte Carlo and
candidate-set approximations, not globally optimized acquisitions. No Monte
Carlo error guarantee or optimizer superiority is claimed.

Limits are 256 observations, 256 candidates and 1,024 posterior draws. Each
fit has an iteration cap and a 30-second timeout. A recorded iteration stop is
a local approximate fit; a failure or timeout refuses the suggestion and
restores its RNG state. Failed or nonfinite reports are refused. The caller
must preserve their physical work; they are not valid GP observations.

`last_diagnostics` exposes the transforms, fitted Gaussian parameters, joint
posterior, base normal samples, acquisition scores and selection. JSON
checkpoints bind space, options and runtime versions and verify a checksum;
restore is atomic. The checksum detects accidental damage, not a malicious
writer. Refitting on continuation is deterministic in the same qualified
single-thread runtime. Pending identities remain owned by `Study`.

Finite algebra, recovery and installed-example checks qualify this implementation.
An accepted final source and any broader effectiveness claims need their own
master-program evidence. This feature activates no automatic defaults.
