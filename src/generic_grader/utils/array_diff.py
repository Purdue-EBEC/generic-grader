"""Helpers to produce human-friendly diffs for numpy arrays."""

import numpy as np

DEFAULT_RTOL = 1e-07
DEFAULT_ATOL = 0.0


def _tolerance_applies(dtype, rtol: float, atol: float) -> bool:
    """Whether ``rtol``/``atol`` should decide equality for arrays of *dtype*.

    Dispatch on ``dtype.kind``: floating (``"f"``) always compares with
    ``np.isclose``/``np.allclose``; integer (``"i"``/``"u"``) compares with
    tolerance only when a tolerance is set.  Integer arrays at exact
    settings (``rtol == 0 and atol == 0``) keep the exact
    ``np.array_equal`` path: ``allclose`` promotes to float64, which would
    call ``2**62 + 1`` equal to ``2**62``.  Every other kind — bool
    (``"b"``), datetime (``"M"``), timedelta (``"m"``), structured
    (``"V"``), object (``"O"``) — compares exactly.  ``kind`` rather than
    ``np.issubdtype`` is required because ``np.timedelta64`` subclasses
    ``np.signedinteger``: the old integer check sent ``m8`` arrays to
    ``np.allclose``, which raises ``UFuncTypeError`` (float64 + m8[s]).
    """
    kind = np.dtype(dtype).kind
    if kind == "f":
        return True
    if kind in ("i", "u"):
        return rtol != 0 or atol != 0
    return False


def _int_not_close(actual, expected, rtol: float, atol: float):
    """Elementwise ``|actual - expected| > atol + rtol * |expected|`` for ints.

    Matches the scalar rule in ``deep_compare`` exactly.  ``np.isclose``
    promotes to float64, which loses integers beyond 2**53 (so
    ``2**62 + 1`` would be close to ``2**62`` at ``atol=0.5``).  Here the
    difference is taken in modular uint64 arithmetic, which is exact for
    any 64-bit integer, and compared against the floored tolerance, which
    is equivalent because the difference is an integer.
    """
    actual = np.asarray(actual)
    expected = np.asarray(expected)
    with np.errstate(over="ignore"):  # 0-d results warn on intended wraparound
        diff = np.maximum(actual, expected).astype(np.uint64) - np.minimum(
            actual, expected
        ).astype(np.uint64)
    delta = np.floor(atol + rtol * np.abs(expected.astype(np.float64)))
    # Tolerances of 2**64 or more admit every uint64 difference.
    unbounded = delta >= 2.0**64
    # A NaN tolerance admits nothing but exact equality.
    undefined = np.isnan(delta)
    limit = np.where(unbounded | undefined, 0.0, delta).astype(np.uint64)
    return ~(unbounded | (diff <= limit)) | (undefined & (diff != 0))


def _diff_mask(actual, expected, rtol: float, atol: float):
    """Boolean mask of elements that differ under the dtype's comparison rule."""
    kind = np.dtype(expected.dtype).kind
    if kind == "f":
        return ~np.isclose(actual, expected, rtol=rtol, atol=atol)
    if kind in ("i", "u") and _tolerance_applies(expected.dtype, rtol, atol):
        return _int_not_close(actual, expected, rtol, atol)
    # Exact elementwise inequality; for structured arrays this can raise
    return actual != expected


def array_diff_details(
    actual,
    expected,
    rtol: float = DEFAULT_RTOL,
    atol: float = DEFAULT_ATOL,
    max_samples: int = 5,
) -> str:
    """Return a short text describing differences between two numpy arrays.

    ``rtol`` and ``atol`` must match the tolerances used to decide equality
    (see :func:`array_compare`) so the reported differences are consistent with
    that decision.
    """

    diff_mask = _diff_mask(actual, expected, rtol, atol)

    # Find indices where arrays differ
    try:
        diff_indices = np.argwhere(diff_mask)
    except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
        diff_indices = None

    details = []
    if diff_indices is not None and diff_indices.size:
        for idx in diff_indices[:max_samples]:
            idx_t = tuple(int(i) for i in idx)
            try:
                exp_val = expected[idx_t]
            except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
                exp_val = "<out-of-bounds>"
            try:
                act_val = actual[idx_t]
            except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
                act_val = "<out-of-bounds>"
            details.append(f"at {idx_t}: expected={exp_val!r}, actual={act_val!r}")
        if _tolerance_applies(expected.dtype, rtol, atol):
            details.append(f"(tolerance: rtol={rtol!r}, atol={atol!r})")
    else:
        details.append(
            "no differing indices found within the reporting tolerance"
            f" (rtol={rtol!r}, atol={atol!r})"
        )

    return "\nDetails: " + "\n".join(details)


def array_compare(
    actual,
    expected,
    rtol: float = DEFAULT_RTOL,
    atol: float = DEFAULT_ATOL,
    max_samples: int = 5,
):
    """Compare two numpy arrays and return (equal, details).

    Integer and floating arrays compare within ``rtol``/``atol``; integer
    arrays at ``rtol == atol == 0`` and all non-numeric dtypes compare
    exactly.  If a numpy comparison function raises, the exception is
    propagated.
    """
    # Check np.array dtype attributes.
    expected_dtype = getattr(expected, "dtype", None)
    try:
        # submitted code could do anything, so be safe.
        actual_dtype = actual.dtype
    except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
        actual_dtype = None

    if expected_dtype != actual_dtype:
        details = "\nNumpy array data types differ.\n"
        details += f"\nExpected dtype={expected_dtype}"
        details += f"\n  Actual dtype={actual_dtype}"
        return False, details

    # Check np.array shape attributes.
    expected_shape = getattr(expected, "shape", None)
    try:
        # submitted code could do anything, so be safe.
        actual_shape = actual.shape
    except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
        actual_shape = None

    if expected_shape != actual_shape:
        details = "\nNumpy array shapes differ.\n"
        details += f"\nExpected shape={expected_shape}"
        details += f"\n  Actual shape={actual_shape}"
        return False, details

    # Compare the values of the arrays.
    if _tolerance_applies(expected.dtype, rtol, atol):
        if expected.dtype.kind in ("i", "u"):
            # Exact equality implies within tolerance; skip the mask math.
            equal = np.array_equal(actual, expected) or not np.any(
                _int_not_close(actual, expected, rtol, atol)
            )
        else:
            equal = np.allclose(actual, expected, rtol=rtol, atol=atol)
    else:
        equal = np.array_equal(actual, expected)

    if equal:
        return True, ""

    return False, array_diff_details(
        actual, expected, rtol=rtol, atol=atol, max_samples=max_samples
    )
