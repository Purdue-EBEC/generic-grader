"""Unit tests for :mod:`generic_grader.utils.octave_static`."""

from __future__ import annotations

import unittest

import pytest

from generic_grader.utils.octave_static import (
    LoopDepthTracker,
    get_comments,
    get_docstring,
    get_tokens,
    read_source,
)


class DummyTest(unittest.TestCase):
    def runTest(self):  # pragma: no cover
        pass


@pytest.fixture()
def test_case():
    return DummyTest()


def _write(tmp, name, text):
    """Convenience: drop *text* into ``tmp/name`` and return the path."""
    path = tmp / name
    path.write_text(text)
    return path


# --------------------------------------------------------------------------- #
# read_source                                                                 #
# --------------------------------------------------------------------------- #


def test_read_source_returns_text(tmp_path, test_case):
    path = _write(tmp_path, "a.m", "x = 1;\n")
    assert read_source(test_case, str(path)) == "x = 1;\n"


def test_read_source_fails_helpfully_when_missing(tmp_path, test_case):
    missing = tmp_path / "nope.m"
    with pytest.raises(AssertionError) as exc:
        read_source(test_case, str(missing))
    assert "Unable to load" in str(exc.value)
    assert str(missing) in str(exc.value)


# --------------------------------------------------------------------------- #
# get_comments                                                                #
# --------------------------------------------------------------------------- #


def test_get_comments_splits_header_and_body(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "% Header line 1\n"
        "% Header line 2\n"
        "x = 1;  % trailing comment\n"
        "# hash-style body comment\n",
    )
    header, body = get_comments(test_case, str(path))
    assert header == ["% Header line 1", "% Header line 2"]
    assert body == ["% trailing comment", "# hash-style body comment"]


def test_get_comments_ignores_percent_inside_strings(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "fprintf('50%% done\\n');\n"
        "% real header comment does not exist because code came first\n",
    )
    header, body = get_comments(test_case, str(path))
    # The literal ``%%`` inside the fprintf string must not be seen
    # as a comment, and the trailing comment on the second line is
    # body because code preceded it.
    assert header == []
    assert body and body[0].startswith("% real header")


def test_get_comments_captures_block_comments(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "%{\n"
        "Block header line A\n"
        "Block header line B\n"
        "%}\n"
        "x = 1;\n"
        "#{\n"
        "body block\n"
        "#}\n",
    )
    header, body = get_comments(test_case, str(path))
    assert len(header) == 1
    assert "Block header line A" in header[0]
    assert len(body) == 1
    assert "body block" in body[0]


# --------------------------------------------------------------------------- #
# get_tokens                                                                  #
# --------------------------------------------------------------------------- #


def test_get_tokens_skips_comments_and_strings(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "% header comment\n"
        "x = 1 + 2;  % trailing\n"
        "y = 'hello world';\n"
        "if x == 3\n"
        "  disp(y);\n"
        "end\n",
    )
    tokens = get_tokens(test_case, str(path))
    # The string body ``hello world`` must not be tokenized; the quote
    # characters themselves survive as tokens because they matter for
    # code length.
    assert "hello" not in tokens
    assert "world" not in tokens
    assert "x" in tokens
    assert "==" in tokens
    assert "disp" in tokens
    assert "end" in tokens


def test_get_tokens_ignores_block_comments(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "%{\n" "This entire block should be invisible.\n" "%}\n" "answer = 42;\n",
    )
    tokens = get_tokens(test_case, str(path))
    assert "This" not in tokens
    assert "answer" in tokens
    assert "42" in tokens


def test_get_tokens_counts_scale_with_program_size(tmp_path, test_case):
    small = _write(tmp_path, "small.m", "x = 1;\n")
    big = _write(
        tmp_path,
        "big.m",
        "\n".join(f"a{i} = {i};" for i in range(20)) + "\n",
    )
    assert len(get_tokens(test_case, str(big))) > 5 * len(
        get_tokens(test_case, str(small))
    )


# --------------------------------------------------------------------------- #
# LoopDepthTracker                                                            #
# --------------------------------------------------------------------------- #


def test_loop_depth_flat_loops():
    tracker = LoopDepthTracker()
    tracker.visit_source(
        "for i = 1:3\n"
        "  disp(i);\n"
        "endfor\n"
        "while true\n"
        "  break;\n"
        "endwhile\n"
    )
    assert tracker.max_depth == 1


def test_loop_depth_nested_loops():
    tracker = LoopDepthTracker()
    tracker.visit_source(
        "for i = 1:3\n"
        "  for j = 1:3\n"
        "    for k = 1:3\n"
        "      disp(i);\n"
        "    end\n"
        "  end\n"
        "end\n"
    )
    assert tracker.max_depth == 3


def test_loop_depth_if_blocks_do_not_count():
    tracker = LoopDepthTracker()
    tracker.visit_source(
        "for i = 1:3\n" "  if i > 1\n" "    disp(i);\n" "  end\n" "end\n"
    )
    assert tracker.max_depth == 1


def test_loop_depth_handles_do_until():
    tracker = LoopDepthTracker()
    tracker.visit_source("do\n  x = x + 1;\nuntil x >= 3\n")
    assert tracker.max_depth == 1


def test_loop_depth_skips_block_comments():
    tracker = LoopDepthTracker()
    tracker.visit_source(
        "%{\n"
        "for i = 1:3\n"
        "  for j = 1:3\n"
        "  end\n"
        "end\n"
        "%}\n"
        "for i = 1:3\n"
        "  disp(i);\n"
        "end\n"
    )
    # The nested loop inside the block comment must NOT count.
    assert tracker.max_depth == 1


def test_loop_depth_ignores_blank_and_comment_only_lines():
    tracker = LoopDepthTracker()
    tracker.visit_source(
        "\n" "% just a comment\n" "for i = 1:3\n" "  disp(i);\n" "end\n"
    )
    assert tracker.max_depth == 1


def test_loop_depth_tolerates_unbalanced_end():
    # An extra ``end`` at the outermost level should be swallowed
    # silently rather than blowing up.
    tracker = LoopDepthTracker()
    tracker.visit_source("end\nfor i = 1:3\n  disp(i);\nend\n")
    assert tracker.max_depth == 1


# --------------------------------------------------------------------------- #
# get_docstring                                                               #
# --------------------------------------------------------------------------- #


def test_get_docstring_returns_leading_comment_block(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "% Author: Ada Lovelace\n"
        "% Assignment: hw01\n"
        "% Date: 1843-10-01\n"
        "\n"
        "x = 1;\n",
    )
    doc = get_docstring(test_case, str(path))
    assert doc is not None
    assert "Author: Ada Lovelace" in doc
    assert "Assignment: hw01" in doc


def test_get_docstring_skips_leading_function_line(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "function y = foo(x)\n"
        "% Header block after the function line\n"
        "% Second line\n"
        "y = x + 1;\n"
        "endfunction\n",
    )
    doc = get_docstring(test_case, str(path))
    assert doc is not None
    assert doc.startswith("Header block")


def test_get_docstring_returns_none_when_absent(tmp_path, test_case):
    path = _write(tmp_path, "a.m", "x = 1;\n")
    assert get_docstring(test_case, str(path)) is None


def test_get_docstring_skips_leading_blank_lines(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "\n\n\n" "% Header block after blank leading lines\n" "x = 1;\n",
    )
    doc = get_docstring(test_case, str(path))
    assert doc is not None
    assert "Header block" in doc


def test_get_docstring_handles_block_comment(tmp_path, test_case):
    path = _write(
        tmp_path,
        "a.m",
        "%{\n" "Author: Ada Lovelace\n" "Assignment: hw01\n" "%}\n" "x = 1;\n",
    )
    doc = get_docstring(test_case, str(path))
    assert doc is not None
    assert "Author: Ada Lovelace" in doc
