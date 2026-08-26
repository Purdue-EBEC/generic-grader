"""Unit tests for :class:`generic_grader.runtimes.python.PythonRuntime`.

The Python runtime is a thin adapter over the legacy
``Importer.import_obj`` + ``custom_stack`` flow, so this file focuses on
the *seam* rather than re-testing the pre-existing behavior of those
two dependencies (which are already covered by ``tests/utils/`` tests).

Concretely we check:

* ``resolve`` delegates to :class:`Importer` and returns whatever it
  returns.  Any refactor that changes how the callable is loaded must
  still land the same object at the seam so downstream ``run`` works.
* ``run`` invokes the callable inside ``custom_stack``, applies the
  caller-provided patches (particularly the ``sys.stdout → log``
  patch), and returns a :class:`RuntimeResult` with the callable's
  return value.
* ``entries`` is intentionally ignored by the Python runtime — stdin
  simulation goes through the ``builtins.input`` patch that
  ``__User__`` installs into ``options.patches``.  This test pins the
  behavior so a well-meaning refactor doesn't accidentally start
  consuming ``entries`` here.
"""

from __future__ import annotations

import sys
import unittest
from io import StringIO
from unittest.mock import patch

from generic_grader.runtimes.base import RuntimeResult
from generic_grader.runtimes.python import PythonRuntime
from generic_grader.utils.options import Options


class _Case(unittest.TestCase):
    """Concrete TestCase we can pass to ``resolve`` without needing
    the full :func:`reference_test` machinery."""

    def runTest(self):  # pragma: no cover — never invoked
        pass


def _make_module_with(name, obj_name, func):
    """Register a synthetic module in ``sys.modules`` so ``Importer``
    can find it.  Yielding a real file under ``tmp_path`` would work
    too but is heavier — the point of these tests is to isolate the
    runtime, not exercise the importer."""
    import types

    module = types.ModuleType(name)
    setattr(module, obj_name, func)
    sys.modules[name] = module
    return module


def test_resolve_returns_imported_callable(fix_syspath):
    """``resolve`` must hand back the exact callable ``Importer``
    found — the ``__User__`` layer treats the return value as opaque
    and passes it straight into ``run``."""

    def target():  # pragma: no cover — resolve doesn't invoke it
        return "hello"

    _make_module_with("resolve_target_module", "target", target)

    options = Options(
        obj_name="target",
        sub_module="resolve_target_module",
        ref_module="resolve_target_module",
        weight=1,
    )
    runtime = PythonRuntime()
    handle = runtime.resolve(_Case(), options, "resolve_target_module")
    assert handle is target


def test_run_calls_target_and_returns_result(fix_syspath):
    """The runtime executes the callable and packages its return
    value into a :class:`RuntimeResult`."""

    def target(x, y):
        return x + y

    options = Options(
        obj_name="target",
        sub_module="m",
        ref_module="m",
        args=(2, 3),
        weight=1,
    )
    runtime = PythonRuntime()
    result = runtime.run(options, target, StringIO(), iter(""))
    assert isinstance(result, RuntimeResult)
    assert result.returned_values == 5


def test_run_applies_options_patches(fix_syspath):
    """``run`` must apply ``options.patches`` (the caller stashes
    stdout/input redirection there).  We assert the observable
    effect: writes to ``sys.stdout`` inside the target land in the
    patched log stream, not the real terminal."""

    log = StringIO()
    options = Options(
        obj_name="target",
        sub_module="m",
        ref_module="m",
        patches=[{"args": ["sys.stdout", log]}],
        weight=1,
    )

    def target():
        print("captured", end="")
        return None

    runtime = PythonRuntime()
    runtime.run(options, target, log, iter(""))
    assert log.getvalue() == "captured"


def test_run_deepcopies_args_and_kwargs(fix_syspath):
    """Args and kwargs are deep-copied before the call, matching the
    legacy behavior — a student that mutates a list argument must
    not corrupt the ``Options`` shared across ref and sub runs."""

    original_list = [1, 2, 3]

    def target(items):
        items.append(999)
        return items

    options = Options(
        obj_name="target",
        sub_module="m",
        ref_module="m",
        args=(original_list,),
        weight=1,
    )
    runtime = PythonRuntime()
    result = runtime.run(options, target, StringIO(), iter(""))
    # The student's mutation lives on the returned list …
    assert result.returned_values == [1, 2, 3, 999]
    # … but the original list stored on ``options`` is untouched.
    assert original_list == [1, 2, 3]


def test_run_ignores_entries(fix_syspath):
    """The Python runtime deliberately does not consume ``entries``
    (stdin simulation is via the ``builtins.input`` patch).  Passing
    an already-exhausted iterator must not raise here — that would
    change the semantics for legacy tests that never opt in to the
    entries feature."""

    def target():
        return 1

    options = Options(obj_name="target", sub_module="m", ref_module="m", weight=1)
    runtime = PythonRuntime()
    # An empty iterator (fully consumed) is what ``__User__`` passes
    # by default; the runtime must accept it.
    result = runtime.run(options, target, StringIO(), iter(""))
    assert result.returned_values == 1


def test_run_lets_target_exceptions_propagate(fix_syspath):
    """Runtime errors from the student's code must bubble up to
    ``__User__.call_obj``, which owns the failure formatting.  If
    ``PythonRuntime.run`` swallowed them, the student-facing message
    would go missing."""

    def target():
        raise ValueError("boom")

    options = Options(obj_name="target", sub_module="m", ref_module="m", weight=1)
    runtime = PythonRuntime()
    try:
        runtime.run(options, target, StringIO(), iter(""))
    except ValueError as e:
        assert str(e) == "boom"
    else:  # pragma: no cover — defensive
        raise AssertionError("Expected ValueError")


def test_resolve_uses_importer(fix_syspath):
    """We verify ``resolve`` really does delegate to ``Importer``
    (rather than reproducing its logic) by patching the importer and
    checking the patched version was called with the exact arguments
    ``__User__`` would pass."""

    sentinel = object()
    with patch(
        "generic_grader.runtimes.python.Importer.import_obj",
        return_value=sentinel,
    ) as mock_import:
        options = Options(obj_name="target", sub_module="m", ref_module="m", weight=1)
        test = _Case()
        runtime = PythonRuntime()
        assert runtime.resolve(test, options, "some_module") is sentinel
        mock_import.assert_called_once_with(test, "some_module", options)
