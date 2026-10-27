# Wallet enclosure argument

The retained synthetic law has independent uniform covariates on [-1,1]^2,
incidence probability logistic(.40-.80*x+.50*y), latent Gaussian mean
.25+.55*x-.30*y+.35*x*y and standard deviation exp(-.60+.30*x).
Coefficients here denote the exact retained binary64 constants. Fees and caps
likewise come from the saved generator. This defines a real-arithmetic extension
of the saved model; NumPy rounding decisions are not certified.

For L normal with mean mu and standard deviation sigma, the censored wallet is
A*max(exp(L)-1,0). Integration of the truncated normal exponential gives the
conditional capped mean used in wallet.py. Alternatively, it is
p*integral_0^cap Phi((mu-log(1+t))/sigma) dt. These identities agree by integration
by parts. Utility is this mean minus the fee, or zero for no action.

To enclose Phi(z), for 0<=z<=8 use

Phi(z) = 1/2 + z*exp(-z^2/2)/sqrt(2*pi) * sum(n>=0) z^(2*n)/(2*n+1)!!.

This follows by differentiating the entire power series (uniformly convergent
on compact sets) and matching Phi(0)=1/2. All terms are positive. After term n,
the next ratio q=z^2/(2*n+3) bounds every later ratio. When q<1, the omitted
tail lies between zero and next_term/(1-q). The stopping threshold controls
remainder width, never the scientific verdict. For z>8, the Mills bound
0<=1-Phi(z)<=exp(-z^2/2)/(z*sqrt(2*pi)) follows by replacing 1 by t/z in the
Gaussian tail integral. Symmetry handles negative z. Monotonicity lets endpoint
enclosures bound any interval argument. All operations use mpmath's directed
interval arithmetic at 30 decimal digits; this is a conditional numerical
certificate trusting that runtime, not a formally verified arithmetic kernel.

At each rectangle, interval arithmetic contains all model and true utilities.
An action whose upper utility is less than the greatest lower utility cannot
maximize the model anywhere in that rectangle. Keep every other action,
including ties. Taking the hull of true utilities over this superset contains
the policy value everywhere. For paired differences, take the hull over the
Cartesian product of possible actions. Identical actions have exactly zero
difference. Regret is max_j (true_u_j-true_u_chosen), with the chosen action
included, so it is nonnegative. Never cancel terms across distinct actions
without a valid interval calculation.

Alternating dyadic splits partition the square. Prefix-free binary paths with
sum 2^(-depth)=1 cover it up to measure-zero edges. Every cell has uniform
probability 2^(-depth). Directed weighted sums of all cell enclosures contain
the population quantities. Replacing a parent only after both children exist
preserves coverage at resource stops. Exact mpf endpoint tuples are authoritative;
printed floats are only approximate displays. A sign is established only when
the whole paired-difference interval lies strictly above or below zero.

There is no guarantee of obtaining a desired width in a fixed budget. Overlap
with zero remains unresolved. These conditional population results for frozen
policies do not establish an expected effect across training seeds, population
identification under unknown missingness, causal identification, or real-bank
effectiveness. Independent quadrature is a diagnostic and cannot narrow an
enclosure or replace the coverage/remainder argument.
