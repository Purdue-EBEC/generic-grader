"""Tests for the host-side `PatchSpec` builders."""

from __future__ import annotations

import json

import pytest

from generic_grader.sandbox.patch_specs import (
    make_iter_patch_spec,
    make_noop_patch_spec,
    make_raise_error_patch_spec,
    make_source_patch_spec,
)
from generic_grader.sandbox.protocol import PatchSpec

# ---------------------------------------------------------------------------
# noop
# ---------------------------------------------------------------------------


def test_noop_basic():
    spec = make_noop_patch_spec("matplotlib.pyplot.show")
    assert spec == PatchSpec(target="matplotlib.pyplot.show", kind="noop")


def test_noop_passes_through_patch_kwargs():
    spec = make_noop_patch_spec("turtle.write", patch_kwargs={"create": True})
    assert spec.patch_kwargs == {"create": True}


# ---------------------------------------------------------------------------
# iter_returns
# ---------------------------------------------------------------------------


def test_iter_returns_records_values_in_order():
    spec = make_iter_patch_spec("random.random", [0.5, 0.25, 0.125])
    assert spec.kind == "iter_returns"
    assert spec.values == [0.5, 0.25, 0.125]


def test_iter_returns_copies_values_so_caller_mutation_is_isolated():
    values = [1, 2, 3]
    spec = make_iter_patch_spec("m.f", values)
    values.append(4)
    assert spec.values == [1, 2, 3]


# ---------------------------------------------------------------------------
# raise_error
# ---------------------------------------------------------------------------


def test_raise_error_uses_qualified_class_name():
    from generic_grader.utils.exceptions import TurtleDoneError

    spec = make_raise_error_patch_spec("turtle.done", TurtleDoneError)
    assert spec.kind == "raise_error"
    assert spec.error_qualname == ("generic_grader.utils.exceptions.TurtleDoneError")


def test_raise_error_rejects_non_exception_classes():
    with pytest.raises(TypeError, match="exception class"):
        make_raise_error_patch_spec("x", "not a class")  # type: ignore[arg-type]


def test_raise_error_rejects_non_exception_subclass():
    with pytest.raises(TypeError, match="exception class"):
        make_raise_error_patch_spec("x", int)


# ---------------------------------------------------------------------------
# source
# ---------------------------------------------------------------------------


def _module_level_fake(time):  # pragma: no cover - source-captured
    return (time * 1234567.89) % 125


def test_source_captures_module_level_function():
    spec = make_source_patch_spec("falling.falling_dist", _module_level_fake)
    assert spec.kind == "source"
    assert spec.name == "_module_level_fake"
    assert "1234567.89" in spec.source


def test_source_rejects_lambda():
    with pytest.raises(ValueError, match="lambda"):
        make_source_patch_spec("x", lambda v: v)


def test_source_rejects_non_callable():
    with pytest.raises(TypeError, match="callable"):
        make_source_patch_spec("x", 42)  # type: ignore[arg-type]


def test_source_dedents_function_defined_in_nested_scope():
    # Functions defined inside a test get indented; inspect.getsource
    # returns the original indentation, so the helper must dedent.
    def _nested(time):  # pragma: no cover - source-captured
        return time + 1

    spec = make_source_patch_spec("m.f", _nested)
    # First non-blank line must be flush-left after dedent.
    first_line = next(line for line in spec.source.splitlines() if line.strip())
    assert first_line.startswith("def ")


def test_source_raises_when_source_unavailable():
    # Builtins are callables whose source cannot be retrieved.
    with pytest.raises(ValueError, match="Cannot capture source"):
        make_source_patch_spec("x", len)


# ---------------------------------------------------------------------------
# JSON portability
# ---------------------------------------------------------------------------


def test_all_specs_are_json_serializable():
    from generic_grader.utils.exceptions import TurtleDoneError

    specs = [
        make_noop_patch_spec("a"),
        make_iter_patch_spec("b", [1, 2]),
        make_raise_error_patch_spec("c", TurtleDoneError),
        make_source_patch_spec("d", _module_level_fake),
    ]
    payload = json.dumps([s.to_dict() for s in specs])
    decoded = [PatchSpec.from_dict(d) for d in json.loads(payload)]
    assert decoded == specs
