"""Safe comparison utilities that avoid O(n²) difflib.ndiff on large data.

unittest's assertEqual delegates to type-specific methods (assertDictEqual,
assertListEqual, assertMultiLineEqual, etc.) that always compute
difflib.ndiff on pprint.pformat() output before truncating.  ndiff has
O(n²) complexity and can hang for minutes on data with ~200+ differing
lines.

safe_assert_equal checks the pprint.pformat() size of both values.  When
the formatted output is small enough, it falls through to assertEqual so
students still see the familiar diff with '^' character-level markers.
When the output is large, it performs a direct != comparison and builds a
truncated error message with reprlib.repr, avoiding the expensive diff.

make_diff produces a unified diff string similar to assertEqual's output,
suitable for inclusion in error messages.
"""

import difflib
import pprint
import reprlib

_MAX_PFORMAT_CHARS = 2000
"""Maximum combined pprint.pformat() length (in characters) before
falling back to the truncated comparison.  At 2000 characters ndiff
completes in well under a second; above that it grows quadratically."""

_safe_repr = reprlib.Repr()
_safe_repr.maxstring = 200
_safe_repr.maxother = 200
_safe_repr.maxdict = 20
_safe_repr.maxlist = 20
_safe_repr.maxtuple = 20
_safe_repr.maxset = 20


def safe_assert_equal(test_case, actual, expected, msg=""):
    """Assert *actual* == *expected* without risking an O(n²) hang.

    For small values the call delegates to ``test_case.assertEqual`` so
    the failure message includes the familiar ndiff output.  For large
    values a direct ``!=`` check is used and the error message shows a
    truncated representation of both sides.
    """
    fmt_actual = pprint.pformat(actual)
    fmt_expected = pprint.pformat(expected)

    if len(fmt_actual) + len(fmt_expected) <= _MAX_PFORMAT_CHARS:
        # Small enough — use assertEqual for nice diff highlighting.
        test_case.maxDiff = None
        test_case.assertEqual(actual, expected, msg=msg)
    else:
        # Too large — compare directly, truncate the repr.
        if actual != expected:
            detail = f"{_safe_repr.repr(actual)} != {_safe_repr.repr(expected)}"
            raise AssertionError(detail + msg)


def make_diff(actual, expected):
    """Create a diff similar to unittest.TestCase.assertEqual.

    Returns an empty string when the combined length exceeds
    ``_MAX_PFORMAT_CHARS`` to avoid an O(n²) hang from difflib.ndiff.
    """
    if len(actual) + len(expected) > _MAX_PFORMAT_CHARS:
        return ""

    # Ensure strings end with a newline to make diff readable.
    expected = expected if expected.endswith("\n") else expected + "\n"
    actual = actual if actual.endswith("\n") else actual + "\n"

    return "".join(
        difflib.ndiff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
        )
    )
