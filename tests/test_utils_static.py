import unittest

import pytest

from generic_grader.utils.static import get_comments, get_tokens


class SomeTest(unittest.TestCase):
    pass


def test_get_tokens_with_token_error(tmp_path):
    """Test that TokenErrors are handled."""

    # Arrange
    file_path = tmp_path / "test.py"
    file_path.write_text("'''spam")  # missing closing triple quote

    # The TokenError should reraise as an AssertionError in unittest.
    with pytest.raises(AssertionError, match="EOF in multi-line string"):
        get_tokens(SomeTest(), file_path)


# Test get_comments function on a file with
#   - no comments
#   - only a header comment
#   - only some body comment
#   - some header and body comment
#   - a header comment that has encoding and newlines and some body comments
comments_test_cases = (
    {
        "lines": ("pass",),
        "expected_comments": (
            [],
            [],
        ),
    },
    {
        "lines": (
            "# Header comment 1",
            "# Header comment 2",
            "pass",
        ),
        "expected_comments": (
            ["# Header comment 1", "# Header comment 2"],
            [],
        ),
    },
    {
        "lines": (
            "pass",
            "# Body comment 1",
            "spam = 5  # Body comment 2",
        ),
        "expected_comments": (
            [],
            ["# Body comment 1", "# Body comment 2"],
        ),
    },
    {
        "lines": (
            "# Header comment 1",
            "# Header comment 2",
            "pass",
            "# Body comment 1",
            "spam = 5  # Body comment 2",
        ),
        "expected_comments": (
            ["# Header comment 1", "# Header comment 2"],
            ["# Body comment 1", "# Body comment 2"],
        ),
    },
    {
        "lines": (
            "# Header comment 1\n\n\n",
            "# Header comment 2",
            "pass",
            "# Body comment 1",
            "spam = 5  # Body comment 2",
        ),
        "expected_comments": (
            ["# Header comment 1", "# Header comment 2"],
            ["# Body comment 1", "# Body comment 2"],
        ),
    },
)


@pytest.mark.parametrize(
    "lines,expected_comments",
    [c.values() for c in comments_test_cases],
)
def test_get_comments(lines, expected_comments, tmp_path):
    # Arrange
    file_path = tmp_path / "test.py"
    file_path.write_text("\n".join(lines))

    # Act
    comments = get_comments(SomeTest(), file_path)

    # Assert
    assert comments == expected_comments
