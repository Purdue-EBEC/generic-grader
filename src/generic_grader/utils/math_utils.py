from math import log10


def n_trials(n, tolerance):
    """
    for a random variable intended to be distributed uniformly over `n` values,
    return the number of trials necessary to check for extra values with the
    chance of missing an extra value reduced to 1 in 1x10^tolerance.

    the worst case scenario is an off by one error where the function produces
    one number it shouldn't.  e.g. returning 100 when asked for a 2 digit
    number.  the probability p of getting this result is only 1 in 91.  i.e. the
    probability of not getting the bad result (1-p) is 90/91.

    we want to call the function enough times to ensure the chance we will miss
    the bad result is very low (e.g. less than 1 in a billion).

        (1-p)^n < 1e-9

    or

        (90/91)^n < 1e-9

    solving for n,

        n = ceil( 9 / log10( (n+1) / n) )

    for the 2 digit case mentioned above, this results in only 1,876 calls to
    reduce the probability of missing the extra value to less than 1 in a
    billion.  for the 3 digit case, we require 18,662 calls.
    """
    return int(1 + tolerance / log10((n + 1) / n))


def calc_log_limit(expected_log):
    """Calculate a log character limit as some minimum number of
    characters plus a multiple of the length of the expected log.
    """
    return int(200 + 1.5 * len(expected_log))
