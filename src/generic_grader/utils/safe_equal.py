"""Safe comparison utilities that bound the cost of difflib.ndiff on huge data.

unittest's assertEqual delegates to type-specific methods (assertDictEqual,
assertListEqual, assertMultiLineEqual, etc.) that compute difflib.ndiff on
pprint.pformat() output.  Before Python 3.14 ndiff was O(n²) when most lines
differ (about 40 s for 57k characters of final project output).  On 3.14+ it
is close to linear, but with a large constant when many short lines differ
slightly (about 12 s per million characters).

safe_assert_equal checks the size of both values (raw length for strings,
pprint.pformat() length otherwise).  Up to ``_MAX_PFORMAT_CHARS`` it falls
through to assertEqual so students see the familiar diff with '^'
character-level markers.  Beyond that it performs a direct != comparison and
builds a truncated error message with reprlib.repr.  Diffs longer than
``_MAX_DIFF_CHARS`` are cut at a line boundary.

make_diff produces a diff string similar to assertEqual's output, suitable
for inclusion in error messages.
"""

import difflib
import pprint
import reprlib

_MAX_PFORMAT_CHARS = 250_000
"""Maximum combined size (in characters) before falling back to the truncated
comparison.  Worst-case ndiff time on 3.14 and 3.15 at this size is about 3 s."""

_MAX_DIFF_CHARS = 500_000
"""Maximum length (in characters) of a diff shown to the student."""

_safe_repr = reprlib.Repr()
_safe_repr.maxstring = 200
_safe_repr.maxother = 200
_safe_repr.maxdict = 20
_safe_repr.maxlist = 20
_safe_repr.maxtuple = 20
_safe_repr.maxset = 20


def safe_repr(value):
    """Return a truncated ``repr`` of *value* that is safe for large data."""
    return _safe_repr.repr(value)


def _size(value):
    """Return the length of the text unittest would diff for *value*."""
    return len(value) if isinstance(value, str) else len(pprint.pformat(value))


def _truncate_diff(diff):
    """Cut *diff* at a line boundary once it exceeds ``_MAX_DIFF_CHARS``."""
    if len(diff) <= _MAX_DIFF_CHARS:
        return diff
    cut = diff.rfind("\n", 0, _MAX_DIFF_CHARS) + 1 or _MAX_DIFF_CHARS
    return diff[:cut] + f"... [diff truncated; {len(diff) - cut} more characters]\n"


def safe_assert_equal(test_case, actual, expected, msg=""):
    """Assert *actual* == *expected* while bounding the cost of huge diffs.

    For small values the call delegates to ``test_case.assertEqual`` so
    the failure message includes the familiar ndiff output.  For large
    values a direct ``!=`` check is used and the error message shows a
    truncated representation of both sides.
    """
    if _size(actual) + _size(expected) <= _MAX_PFORMAT_CHARS:
        # Small enough — use assertEqual for nice diff highlighting.
        test_case.maxDiff = None
        # Private unittest attribute; strings over 2**16 characters skip the diff.
        test_case._diffThreshold = _MAX_PFORMAT_CHARS
        try:
            test_case.assertEqual(actual, expected)
        except AssertionError as e:
            # Truncate the diff only, so the trailing hint in msg survives.
            raise test_case.failureException(
                test_case._formatMessage(msg, _truncate_diff(str(e)))
            ) from None
    else:
        # Too large — compare directly, truncate the repr.
        if actual != expected:
            detail = f"{_safe_repr.repr(actual)} != {_safe_repr.repr(expected)}"
            raise AssertionError(detail + msg)


def make_diff(actual, expected):
    """Create a diff similar to unittest.TestCase.assertEqual.

    Returns an empty string when the combined length exceeds
    ``_MAX_PFORMAT_CHARS`` to bound the cost of difflib.ndiff, and cuts
    the diff at ``_MAX_DIFF_CHARS``.
    """
    if len(actual) + len(expected) > _MAX_PFORMAT_CHARS:
        return ""

    # Ensure strings end with a newline to make diff readable.
    expected = expected if expected.endswith("\n") else expected + "\n"
    actual = actual if actual.endswith("\n") else actual + "\n"

    return _truncate_diff(
        "".join(
            difflib.ndiff(
                actual.splitlines(keepends=True),
                expected.splitlines(keepends=True),
            )
        )
    )
