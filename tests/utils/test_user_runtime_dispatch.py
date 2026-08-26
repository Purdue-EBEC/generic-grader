"""Verify ``__User__.call_obj`` translates runtime-level exceptions
into student-facing failures.

The Python code path is already covered by ``tests/utils/test_user.py``.
This file focuses on the *new* Octave-specific except-branches added
alongside the runtime dispatch, since those are the only user-visible
divergence from the pre-runtime behavior.

We stub out ``OctaveRuntime.run`` — the Octave subprocess itself has
its own dedicated tests in ``tests/runtimes/test_octave.py`` — so
these tests run in milliseconds and require no external binary.
"""

from __future__ import annotations

import unittest

import pytest

from generic_grader.runtimes.octave import (
    OctaveNotInstalledError,
    OctaveRuntime,
    OctaveRuntimeError,
    OctaveTimeoutError,
)
from generic_grader.utils.options import Options
from generic_grader.utils.user import RefUser, SubUser


class _FakeCase(unittest.TestCase):
    def runTest(self):  # pragma: no cover — never invoked
        pass


def _make_user(fix_syspath, monkeypatch, exc, cls=SubUser):
    """Build a real ``SubUser`` (or ``RefUser``) pointing at an
    Octave-language ``Options`` whose ``run`` raises ``exc``."""

    # A file must exist so ``resolve`` succeeds \u2014 we're only
    # exercising ``run``.
    module = "sub_prog" if cls is SubUser else "ref_prog"
    (fix_syspath / f"{module}.m").write_text("disp('placeholder')\n")

    options = Options(
        language="octave",
        obj_name="sub_prog" if cls is SubUser else "ref_prog",
        sub_module="sub_prog",
        ref_module="ref_prog",
        weight=1,
    )

    def fake_run(self, opts, handle, log, entries):
        raise exc

    monkeypatch.setattr(OctaveRuntime, "run", fake_run)
    return cls(_FakeCase(), options=options)


def test_octave_timeout_becomes_timeouterror_failure(fix_syspath, monkeypatch):
    """A wall-clock timeout inside the Octave subprocess is presented
    to the student as a ``TimeoutError`` with the runtime's message
    quoted in the hint block."""
    user = _make_user(
        fix_syspath,
        monkeypatch,
        OctaveTimeoutError("took longer than 1 second(s)"),
    )
    # ``test.fail`` swaps ``failureException`` to ``TimeoutError``
    # before raising — that swap is exactly what surfaces the
    # timeout to the runner instead of the default ``AssertionError``.
    with pytest.raises(TimeoutError) as excinfo:
        user.call_obj()
    assert user.test.failureException is TimeoutError
    assert "took longer than" in str(excinfo.value)


def test_octave_runtime_error_shows_stderr_hint(fix_syspath, monkeypatch):
    """Nonzero-exit Octave failures propagate the child's stderr —
    the message that already points at the offending ``.m`` line —
    into the hint block of the student-facing failure."""
    user = _make_user(
        fix_syspath,
        monkeypatch,
        OctaveRuntimeError(
            "Octave exited with code 1", stderr="error: 'foo' undefined"
        ),
    )
    with pytest.raises(RuntimeError) as excinfo:
        user.call_obj()
    assert user.test.failureException is RuntimeError
    assert "'foo' undefined" in str(excinfo.value)


def test_octave_runtime_error_empty_stderr_falls_back_to_message(
    fix_syspath, monkeypatch
):
    """If Octave exits nonzero with an empty stderr (rare, but
    possible if the child is killed via SIGKILL from outside), we
    still show *something* useful \u2014 the exception message."""
    user = _make_user(
        fix_syspath,
        monkeypatch,
        OctaveRuntimeError("Octave exited with code 137", stderr=""),
    )
    with pytest.raises(RuntimeError) as excinfo:
        user.call_obj()
    assert "Octave exited with code 137" in str(excinfo.value)


def test_octave_not_installed_surfaces_grader_config_error(fix_syspath, monkeypatch):
    """When Octave is missing on the grader host, the failure is a
    configuration bug \u2014 not a student mistake \u2014 so the message
    doesn't reference the student's code."""
    user = _make_user(
        fix_syspath,
        monkeypatch,
        OctaveNotInstalledError("The Octave executable ('octave') was not found"),
    )
    with pytest.raises(RuntimeError) as excinfo:
        user.call_obj()
    assert user.test.failureException is RuntimeError
    msg = str(excinfo.value)
    assert "not found" in msg
    # The student-blaming preamble ('Your `...` malfunctioned') is
    # deliberately absent for grader-configuration errors.
    assert "malfunctioned" not in msg


def test_octave_error_branches_work_for_refuser_too(fix_syspath, monkeypatch):
    """``RefUser`` and ``SubUser`` both go through ``call_obj`` \u2014
    the reference run must surface the same errors so the grader can
    tell if the *reference* code is what's broken."""
    user = _make_user(
        fix_syspath,
        monkeypatch,
        OctaveTimeoutError("took longer than 1 second"),
        cls=RefUser,
    )
    with pytest.raises(TimeoutError):
        user.call_obj()
    assert user.test.failureException is TimeoutError
