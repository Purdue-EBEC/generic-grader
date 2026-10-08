"""End-to-end tests that the four newly-Octave-capable test types

(``style.comments``, ``style.program_length``, ``style.docstring``,
``function.static_loop_depth``) actually dispatch through
:mod:`generic_grader.utils.octave_static` when ``language=\"octave\"``
and produce the same PASS / FAIL behaviour that the Python variant
does on equivalent files.

These tests deliberately do not require GNU Octave to be installed \u2014
everything they exercise is pure Python parsing of ``.m`` source.
"""

from __future__ import annotations

import unittest

import pytest

from generic_grader.function.static_loop_depth import build as build_loop_depth
from generic_grader.style.comments import build as build_comments
from generic_grader.style.docstring import build as build_docstring
from generic_grader.style.program_length import build as build_program_length
from generic_grader.utils.options import Options


def _run_first(built_class: type, method_prefix: str) -> tuple[bool, str]:
    """Instantiate *built_class* and run its first parametrized method.

    Returns ``(passed, message)`` so the caller can assert either
    outcome.  All other exceptions propagate so real bugs still fail
    the test loudly.
    """

    method_name = f"{method_prefix}_0"
    if not hasattr(built_class, method_name):
        method_name = method_prefix  # non-parametrized method (docstring)
    instance = built_class(methodName=method_name)
    try:
        getattr(instance, method_name)()
    except unittest.TestCase.failureException as exc:
        return False, str(exc)
    return True, ""


# --------------------------------------------------------------------------- #
# style.comments                                                              #
# --------------------------------------------------------------------------- #


def test_style_comments_passes_when_submission_is_well_commented(fix_syspath):
    ref_src = (
        "% Ref header\n"
        "x = 1;  % explain x\n"
        "y = 2;  % explain y\n"
        "z = 3;  % explain z\n"
    )
    sub_src = (
        "% Sub header\n"
        "x = 1;  % explain x\n"
        "y = 2;  % explain y\n"
        "z = 3;  % explain z another way\n"
    )
    (fix_syspath / "ref.m").write_text(ref_src)
    (fix_syspath / "sub.m").write_text(sub_src)

    options = Options(
        sub_module="sub",
        ref_module="ref",
        weight=1,
        language="octave",
    )
    built = build_comments(options)
    passed, message = _run_first(built, "test_comment_length")
    assert passed, message


def test_style_comments_fails_when_submission_has_too_few_comments(fix_syspath):
    ref_src = "\n".join(
        [f"x{i} = {i};  % explanation number {i} here" for i in range(20)]
    )
    sub_src = "\n".join([f"x{i} = {i};" for i in range(20)])
    (fix_syspath / "ref.m").write_text(ref_src)
    (fix_syspath / "sub.m").write_text(sub_src)

    options = Options(
        sub_module="sub",
        ref_module="ref",
        weight=1,
        language="octave",
    )
    built = build_comments(options)
    passed, message = _run_first(built, "test_comment_length")
    assert not passed
    assert "too few comments" in message


# --------------------------------------------------------------------------- #
# style.program_length                                                        #
# --------------------------------------------------------------------------- #


def test_style_program_length_passes_for_similar_size(fix_syspath):
    ref_src = "\n".join([f"x{i} = {i};" for i in range(10)])
    sub_src = "\n".join([f"y{i} = {i};" for i in range(10)])
    (fix_syspath / "ref.m").write_text(ref_src)
    (fix_syspath / "sub.m").write_text(sub_src)

    options = Options(
        sub_module="sub",
        ref_module="ref",
        weight=1,
        language="octave",
    )
    built = build_program_length(options)
    passed, message = _run_first(built, "test_program_length")
    assert passed, message


def test_style_program_length_fails_when_submission_is_bloated(fix_syspath):
    ref_src = "x = 1;\n"
    sub_src = "\n".join([f"x{i} = {i};" for i in range(50)])
    (fix_syspath / "ref.m").write_text(ref_src)
    (fix_syspath / "sub.m").write_text(sub_src)

    options = Options(
        sub_module="sub",
        ref_module="ref",
        weight=1,
        language="octave",
    )
    built = build_program_length(options)
    passed, message = _run_first(built, "test_program_length")
    assert not passed
    assert "bigger than expected" in message


# --------------------------------------------------------------------------- #
# style.docstring                                                             #
# --------------------------------------------------------------------------- #


_GOOD_HEADER = (
    "% Author: Ada Lovelace, lovelace@purdue.edu\n"
    "% Assignment: mm.n - Sub\n"
    "% Date: 2026-08-26\n"
    "%\n"
    "% Description\n"
    "% This program does some things and prints some other things.\n"
    "% It is well documented and quite pleasant.\n"
    "%\n"
    "% Contributors\n"
    "% None\n"
    "%\n"
    "% Academic Integrity Statement\n"
    "% I have not used source code obtained from any unauthorized\n"
    "% source, either modified or unmodified; nor have I provided\n"
    "% another student access to my code.  The project I am\n"
    "% submitting is my own original work.\n"
    "\n"
)


def _write_docstring_pair(root, sub_header, ref_header=_GOOD_HEADER):
    (root / "ref.m").write_text(ref_header + "x = 1;\n")
    (root / "sub.m").write_text(sub_header + "x = 1;\n")


def test_style_docstring_module_passes_for_octave_header(fix_syspath):
    _write_docstring_pair(fix_syspath, _GOOD_HEADER)
    options = Options(sub_module="sub", ref_module="ref", weight=1, language="octave")
    built = build_docstring(options)
    # ``test_docstring_module`` is non-parametrized \u2014 no ``_0`` suffix.
    instance = built(methodName="test_docstring_module")
    instance.test_docstring_module()  # should not raise


def test_style_docstring_module_fails_when_docstring_missing(fix_syspath):
    _write_docstring_pair(fix_syspath, sub_header="")
    options = Options(sub_module="sub", ref_module="ref", weight=1, language="octave")
    built = build_docstring(options)
    instance = built(methodName="test_docstring_module")
    with pytest.raises(AssertionError) as exc:
        instance.test_docstring_module()
    assert "docstring was not found" in str(exc.value)


def test_style_docstring_author_reads_octave_header(fix_syspath):
    _write_docstring_pair(fix_syspath, _GOOD_HEADER)
    options = Options(sub_module="sub", ref_module="ref", weight=1, language="octave")
    built = build_docstring(options)
    instance = built(methodName="test_docstring_author_0")
    instance.test_docstring_author_0()  # should pass


def test_style_docstring_description_length_is_measured(fix_syspath):
    # Submission has almost no description; reference has plenty \u2014
    # this should fail with the "too short" message.
    short_header = (
        "% Author: Ada Lovelace, lovelace@purdue.edu\n"
        "% Assignment: mm.n - Sub\n"
        "% Date: 2026-08-26\n"
        "%\n"
        "% Description\n"
        "% x\n"
        "%\n"
        "% Contributors\n"
        "% None\n"
        "%\n"
        "% Academic Integrity Statement\n"
        "% I have not used source code obtained from any unauthorized\n"
        "% source, either modified or unmodified; nor have I provided\n"
        "% another student access to my code.  The project I am\n"
        "% submitting is my own original work.\n"
        "\n"
    )
    _write_docstring_pair(fix_syspath, short_header)
    options = Options(sub_module="sub", ref_module="ref", weight=1, language="octave")
    built = build_docstring(options)
    instance = built(methodName="test_docstring_desc_0")
    with pytest.raises(AssertionError) as exc:
        instance.test_docstring_desc_0()
    assert "too short" in str(exc.value)


# --------------------------------------------------------------------------- #
# function.static_loop_depth                                                  #
# --------------------------------------------------------------------------- #


def test_static_loop_depth_passes_when_meets_minimum(fix_syspath):
    (fix_syspath / "sub.m").write_text(
        "function y = do_stuff(x)\n"
        "  for i = 1:x\n"
        "    for j = 1:x\n"
        "      disp(i * j);\n"
        "    end\n"
        "  end\n"
        "endfunction\n"
    )
    options = Options(
        sub_module="sub",
        obj_name="do_stuff",
        weight=1,
        language="octave",
        expected_minimum_depth=2,
    )
    built = build_loop_depth(options)
    passed, message = _run_first(built, "test_static_loop_depth")
    assert passed, message


def test_static_loop_depth_fails_when_below_minimum(fix_syspath):
    (fix_syspath / "sub.m").write_text(
        "function y = do_stuff(x)\n" "  y = x + 1;\n" "endfunction\n"
    )
    options = Options(
        sub_module="sub",
        obj_name="do_stuff",
        weight=1,
        language="octave",
        expected_minimum_depth=1,
    )
    built = build_loop_depth(options)
    passed, message = _run_first(built, "test_static_loop_depth")
    assert not passed
    assert "doesn't have any loops" in message


def test_static_loop_depth_fails_for_missing_file(fix_syspath):
    options = Options(
        sub_module="nope",
        obj_name="do_stuff",
        weight=1,
        language="octave",
        expected_minimum_depth=1,
    )
    built = build_loop_depth(options)
    passed, message = _run_first(built, "test_static_loop_depth")
    assert not passed
    assert "Unable to load" in message
