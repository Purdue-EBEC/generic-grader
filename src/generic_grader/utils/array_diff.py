"""Helpers to produce human-friendly diffs for numpy arrays."""

import numpy as np


def array_diff_details(actual, expected, max_samples: int = 5) -> str:
    """Return a short text describing differences between two numpy arrays."""

    if np.issubdtype(expected.dtype, np.floating):
        diff_mask = ~np.isclose(actual, expected)
    else:
        # Use elementwise inequality; for structured arrays this can raise
        diff_mask = actual != expected

    # Find indices where arrays differ
    try:
        diff_indices = np.argwhere(diff_mask)
    except Exception:
        diff_indices = None

    details = []
    if diff_indices is not None and diff_indices.size:
        for idx in diff_indices[:max_samples]:
            idx_t = tuple(int(i) for i in idx)
            try:
                exp_val = expected[idx_t]
            except Exception:
                exp_val = "<out-of-bounds>"
            try:
                act_val = actual[idx_t]
            except Exception:
                act_val = "<out-of-bounds>"
            details.append(f"at {idx_t}: expected={exp_val!r}, actual={act_val!r}")
    else:
        details.append("no differing indices found")

    return "\nDetails: " + "\n".join(details)


def array_compare(
    actual, expected, rtol: float = 1e-07, atol: float = 0.0, max_samples: int = 5
):
    """Compare two numpy arrays and return (equal, details).

    If a numpy comparison function raises, the exception is propagated.
    """
    # Check np.array dtype attributes.
    expected_dtype = getattr(expected, "dtype", None)
    try:
        # submitted code could do anything, so be safe.
        actual_dtype = actual.dtype
    except Exception:
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
    except Exception:
        actual_shape = None

    if expected_shape != actual_shape:
        details = "\nNumpy array shapes differ.\n"
        details += f"\nExpected shape={expected_shape}"
        details += f"\n  Actual shape={actual_shape}"
        return False, details

    # Compare the values of the arrays.
    if np.issubdtype(expected.dtype, np.floating):
        equal = np.allclose(actual, expected, rtol=rtol, atol=atol)
    else:
        equal = np.array_equal(actual, expected)

    if equal:
        return True, ""

    return False, array_diff_details(actual, expected, max_samples=max_samples)
