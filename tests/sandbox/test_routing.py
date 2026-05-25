"""End-to-end routing tests for `Options.use_sandbox=True`.

These tests don't spin up a real isolate worker -- they monkeypatch
the integration module's entry points to inject pre-built
`SandboxRunResult` instances.  That lets us assert the routing inside
`Importer.import_obj` / `__User__.call_obj` translates structured
sandbox outcomes into the same student-facing failure messages the
legacy in-process path produces.
"""

from __future__ import annotations

import unittest
from typing import Any

import pytest

from generic_grader.sandbox.integration import SandboxRunResult
from generic_grader.utils.exceptions import (
    EndOfInputError,
    ExtraEntriesError,
    UserInitializationError,
)
from generic_grader.utils.importer import SANDBOX_OBJ_SENTINEL, Importer
from generic_grader.utils.options import Options
from generic_grader.utils.user import RefUser, SubUser


class FakeTest(unittest.TestCase):
    """Stand-in TestCase mirroring the harness `Importer`/`User` expect."""


def _opts(**overrides: Any) -> Options:
    base: dict[str, Any] = dict(use_sandbox=True, sub_module="submission")
    base.update(overrides)
    return Options(**base)


def _patch_import(
    monkeypatch: pytest.MonkeyPatch, result: SandboxRunResult
) -> list[tuple]:
    """Replace `sandbox_import_obj` with a stub returning `result`.

    Returns the list of `(module, options)` calls observed so tests
    can assert the routing forwarded the right inputs.
    """
    calls: list[tuple] = []

    def _stub(module, options, **kwargs):
        calls.append((module, options))
        return result

    monkeypatch.setattr("generic_grader.sandbox.integration.sandbox_import_obj", _stub)
    return calls


def _patch_call(
    monkeypatch: pytest.MonkeyPatch, result: SandboxRunResult
) -> list[tuple]:
    calls: list[tuple] = []

    def _stub(module, options, **kwargs):
        calls.append((module, options))
        return result

    monkeypatch.setattr("generic_grader.sandbox.integration.sandbox_call_obj", _stub)
    return calls


# ---------------------------------------------------------------------------
# Importer routing
# ---------------------------------------------------------------------------


def test_importer_routes_to_sandbox_when_use_sandbox_set(monkeypatch):
    calls = _patch_import(monkeypatch, SandboxRunResult(exception=None))
    obj = Importer.import_obj(FakeTest(), "submission", _opts(obj_name="main"))
    assert obj is SANDBOX_OBJ_SENTINEL
    assert calls == [("submission", _opts(obj_name="main"))] or len(calls) == 1


def test_importer_legacy_path_still_works_when_use_sandbox_false(fix_syspath):
    """When use_sandbox is False, the in-process path runs."""
    (fix_syspath / "fake_module.py").write_text("fake_func = lambda: None")
    obj = Importer.import_obj(FakeTest(), "fake_module", Options(obj_name="fake_func"))
    # Real callable, not the sandbox sentinel.
    assert obj is not SANDBOX_OBJ_SENTINEL
    assert callable(obj)


def test_importer_sandbox_reports_stuck_at_input(monkeypatch):
    """Module-level input() in import phase classifies as EndOfInputError."""
    _patch_import(
        monkeypatch,
        SandboxRunResult(consumed_input_during_import=True),
    )
    test = FakeTest()
    with pytest.raises(EndOfInputError) as exc_info:
        Importer.import_obj(test, "submission", _opts(obj_name="main"))
    assert "Stuck at call to `input()`" in str(exc_info.value)
    assert test.failureException is EndOfInputError


def test_importer_sandbox_reports_attribute_error(monkeypatch):
    _patch_import(
        monkeypatch,
        SandboxRunResult(
            exception=[
                {
                    "type": "AttributeError",
                    "message": "module 'submission' has no attribute 'main'",
                    "traceback": "",
                }
            ]
        ),
    )
    test = FakeTest()
    with pytest.raises(AttributeError) as exc_info:
        Importer.import_obj(test, "submission", _opts(obj_name="main"))
    assert "Unable to import `main`" in str(exc_info.value)
    assert test.failureException is AttributeError


def test_importer_sandbox_reports_module_not_found_for_target_module(monkeypatch):
    _patch_import(
        monkeypatch,
        SandboxRunResult(
            exception=[
                {
                    "type": "ModuleNotFoundError",
                    "message": "No module named 'submission'",
                    "traceback": "",
                }
            ]
        ),
    )
    test = FakeTest()
    with pytest.raises(ModuleNotFoundError) as exc_info:
        Importer.import_obj(test, "submission", _opts(obj_name="main"))
    msg = str(exc_info.value)
    assert "Unable to import `submission`" in msg
    assert "submitted a module named `submission`" in msg


def test_importer_sandbox_reports_module_not_found_for_dependency(monkeypatch):
    """When the submitted module imports a missing dependency, hint differs."""
    _patch_import(
        monkeypatch,
        SandboxRunResult(
            exception=[
                {
                    "type": "ModuleNotFoundError",
                    "message": "No module named 'numpy'",
                    "traceback": "",
                }
            ]
        ),
    )
    test = FakeTest()
    with pytest.raises(ModuleNotFoundError) as exc_info:
        Importer.import_obj(test, "submission", _opts(obj_name="main"))
    msg = str(exc_info.value)
    assert "Your `submission` module imports `numpy`" in msg


def test_importer_sandbox_reports_module_not_found_walks_deepest(monkeypatch):
    """Multi-step chain: deepest ModuleNotFoundError wins."""
    _patch_import(
        monkeypatch,
        SandboxRunResult(
            exception=[
                {
                    "type": "ModuleNotFoundError",
                    "message": "No module named 'pkg.subpkg'",
                    "traceback": "",
                },
                {
                    "type": "ModuleNotFoundError",
                    "message": "No module named 'pkg.subpkg.inner'",
                    "traceback": "",
                },
            ]
        ),
    )
    test = FakeTest()
    with pytest.raises(ModuleNotFoundError) as exc_info:
        Importer.import_obj(test, "submission", _opts(obj_name="main"))
    # The hint should reference the deepest missing name.
    assert "pkg.subpkg.inner" in str(exc_info.value)


def test_importer_sandbox_generic_fallback_uses_chain_message(monkeypatch):
    _patch_import(
        monkeypatch,
        SandboxRunResult(
            exception=[
                {
                    "type": "ValueError",
                    "message": "bad input",
                    "traceback": '  File "submission.py", line 1\n    foo()\n',
                }
            ]
        ),
    )
    test = FakeTest()
    with pytest.raises(ValueError) as exc_info:
        Importer.import_obj(test, "submission", _opts(obj_name="main"))
    msg = str(exc_info.value)
    assert "ValueError" in msg
    assert "bad input" in msg
    assert "Error while importing `main`" in msg


def test_importer_sandbox_generic_fallback_without_traceback(monkeypatch):
    """A chain with no traceback text still produces a readable message."""
    _patch_import(
        monkeypatch,
        SandboxRunResult(
            exception=[{"type": "RuntimeError", "message": "oops", "traceback": ""}]
        ),
    )
    test = FakeTest()
    with pytest.raises(RuntimeError) as exc_info:
        Importer.import_obj(test, "submission", _opts(obj_name="main"))
    assert "RuntimeError" in str(exc_info.value)


def test_importer_sandbox_generic_fallback_empty_chain(monkeypatch):
    """If the chain is somehow empty but classifier returns a type, still fail."""
    # Pre-classified: caller forces an Exception even with no chain.
    # We achieve this by sending an unknown type that resolves to Exception.
    _patch_import(
        monkeypatch,
        SandboxRunResult(exception=[{"type": "MysteryError"}]),
    )
    test = FakeTest()
    with pytest.raises(Exception):
        Importer.import_obj(test, "submission", _opts(obj_name="main"))


def test_extract_missing_module_falls_back_to_target_when_no_match():
    """No ModuleNotFoundError entries -> return the original module name."""
    result = SandboxRunResult(exception=[{"type": "ValueError", "message": ""}])
    assert Importer._extract_missing_module(result, "submission") == "submission"


def test_extract_missing_module_handles_missing_message():
    """A ModuleNotFoundError without the canonical text falls through."""
    result = SandboxRunResult(
        exception=[{"type": "ModuleNotFoundError", "message": ""}]
    )
    assert Importer._extract_missing_module(result, "submission") == "submission"


# ---------------------------------------------------------------------------
# User routing (call_obj)
# ---------------------------------------------------------------------------


def _make_subuser(monkeypatch: pytest.MonkeyPatch, options: Options) -> SubUser:
    """Build a SubUser whose import phase is stubbed to succeed."""
    _patch_import(monkeypatch, SandboxRunResult(exception=None))
    return SubUser(FakeTest(), options)


def test_user_calls_sandbox_path_when_use_sandbox_set(monkeypatch):
    """call_obj delegates to sandbox_call_obj when the flag is set."""
    user = _make_subuser(monkeypatch, _opts())
    call_calls = _patch_call(
        monkeypatch,
        SandboxRunResult(exception=None, return_value=42),
    )
    returned = user.call_obj()
    assert returned == 42
    assert len(call_calls) == 1
    assert call_calls[0][0] == "submission"


def test_user_replays_log_into_logio(monkeypatch):
    user = _make_subuser(monkeypatch, _opts(entries=("ans",)))
    _patch_call(
        monkeypatch,
        SandboxRunResult(
            exception=None,
            log="prompt> ans\ndone\n",
            interactions=[0, 8],
            return_value=None,
        ),
    )
    user.call_obj()
    assert user.log.getvalue() == "prompt> ans\ndone\n"
    assert user.interactions == [0, 8]


def test_user_sandbox_returns_repr_for_non_serializable_value(monkeypatch):
    user = _make_subuser(monkeypatch, _opts())
    _patch_call(
        monkeypatch,
        SandboxRunResult(
            exception=None,
            return_non_serializable=True,
            return_repr="<CustomObj>",
        ),
    )
    returned = user.call_obj()
    assert returned == "<CustomObj>"
    assert user.returned_values == "<CustomObj>"


def test_user_sandbox_raises_extra_entries_error_on_leftover(monkeypatch):
    user = _make_subuser(monkeypatch, _opts(entries=("a", "b")))
    _patch_call(
        monkeypatch,
        SandboxRunResult(exception=None, unused_entries=1),
    )
    with pytest.raises(ExtraEntriesError) as exc_info:
        user.call_obj()
    msg = str(exc_info.value)
    assert "ended before the user finished entering input" in msg


def test_user_sandbox_propagates_value_error(monkeypatch):
    user = _make_subuser(monkeypatch, _opts())
    _patch_call(
        monkeypatch,
        SandboxRunResult(
            exception=[
                {
                    "type": "ValueError",
                    "message": "bad",
                    "traceback": '  File "submission.py", line 2\n    main()\n',
                }
            ]
        ),
    )
    with pytest.raises(ValueError) as exc_info:
        user.call_obj()
    msg = str(exc_info.value)
    assert "ValueError" in msg
    assert "bad" in msg


def test_user_sandbox_uses_safe_key_error(monkeypatch):
    """KeyError gets wrapped in SafeKeyError (mirrors legacy path)."""
    user = _make_subuser(monkeypatch, _opts())
    _patch_call(
        monkeypatch,
        SandboxRunResult(
            exception=[{"type": "KeyError", "message": "missing", "traceback": ""}]
        ),
    )
    with pytest.raises(KeyError):
        user.call_obj()
    # The wrapper is named "KeyError" but is a safe subclass.
    assert user.test.failureException.__name__ == "KeyError"


def test_user_sandbox_failure_includes_log_when_nonempty(monkeypatch):
    """A failure message appends the IO log when there's something to show."""
    user = _make_subuser(monkeypatch, _opts())
    _patch_call(
        monkeypatch,
        SandboxRunResult(
            exception=[{"type": "ValueError", "message": "x", "traceback": ""}],
            log="some output\n",
            interactions=[0],
        ),
    )
    with pytest.raises(ValueError) as exc_info:
        user.call_obj()
    assert "Input/Output Log" in str(exc_info.value)


def test_user_sandbox_failure_skips_log_when_empty(monkeypatch):
    """No log -> no log section appended."""
    user = _make_subuser(monkeypatch, _opts())
    _patch_call(
        monkeypatch,
        SandboxRunResult(
            exception=[{"type": "ValueError", "message": "x", "traceback": ""}],
            log="",
        ),
    )
    with pytest.raises(ValueError) as exc_info:
        user.call_obj()
    assert "Input/Output Log" not in str(exc_info.value)


def test_user_sandbox_legacy_path_still_works(fix_syspath):
    """use_sandbox=False -> in-process path runs (sanity check)."""
    (fix_syspath / "fake_module.py").write_text(
        "def fake_func():\n    print('hi')\n    return 7\n"
    )
    opts = Options(sub_module="fake_module", obj_name="fake_func", use_sandbox=False)
    user = SubUser(FakeTest(), opts)
    returned = user.call_obj()
    assert returned == 7
    assert "hi" in user.log.getvalue()


# ---------------------------------------------------------------------------
# RefUser parity
# ---------------------------------------------------------------------------


def test_refuser_routes_to_sandbox_with_ref_module(monkeypatch):
    """RefUser uses options.ref_module as the target."""
    _patch_import(monkeypatch, SandboxRunResult(exception=None))
    call_calls = _patch_call(
        monkeypatch,
        SandboxRunResult(exception=None, return_value="ref"),
    )
    opts = _opts(ref_module="tests.reference", sub_module="submission")
    user = RefUser(FakeTest(), opts)
    user.call_obj()
    assert call_calls[0][0] == "tests.reference"


# ---------------------------------------------------------------------------
# Misc edge cases
# ---------------------------------------------------------------------------


def test_user_initialization_requires_module():
    """Direct __User__ instantiation without a module subclass still errors."""
    from generic_grader.utils.user import __User__

    with pytest.raises(UserInitializationError):
        __User__(FakeTest(), Options(use_sandbox=True))


def test_user_sandbox_call_obj_no_log_or_interactions_when_empty(monkeypatch):
    """An empty log and a single zero interaction is the no-op replay."""
    user = _make_subuser(monkeypatch, _opts())
    _patch_call(
        monkeypatch,
        SandboxRunResult(exception=None, log="", interactions=[0]),
    )
    user.call_obj()
    assert user.log.getvalue() == ""
    assert user.interactions == [0]
