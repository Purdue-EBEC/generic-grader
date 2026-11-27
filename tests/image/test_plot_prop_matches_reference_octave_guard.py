"""Tests that ``image.plot_prop_matches_reference`` refuses to run
unsupported Octave props before spawning a subprocess.

These deliberately do NOT depend on Octave being installed: the guard
must fire before ``RefUser``/``SubUser`` are constructed so a
misconfigured suite fails fast on any host.
"""

from __future__ import annotations

import pytest

from generic_grader.image.plot_prop_matches_reference import build
from generic_grader.utils.octave_plot import SUPPORTED_PROPS
from generic_grader.utils.options import Options

# Every prop that ``utils.plot`` supports but ``utils.octave_plot`` does
# not \u2014 the guard should reject each with the shared error message.
UNSUPPORTED_PROPS = [
    "number of bars",
    "bar widths",
    "x time data",
    "wedge labels",
    "wedge colors",
    "wedge angles",
    "grid lines",
    "legend",
    "spine visibility",
    "position of each spine",
]


@pytest.mark.parametrize("prop", UNSUPPORTED_PROPS)
def test_unsupported_octave_prop_fails_fast(prop, fix_syspath):
    """The guard must fail the test *before* any Octave subprocess runs.

    A pure-Python invocation is enough because we only care about the
    dispatch check; the failure message must also list all currently
    supported props so a grader can pick a viable one.
    """

    options = Options(
        sub_module="sub",
        ref_module="ref",
        obj_name="do_stuff",
        weight=1,
        language="octave",
        prop=prop,
    )
    built_class = build(options)
    instance = built_class(methodName="test_plot_prop_matches_reference_0")
    with pytest.raises(AssertionError) as exc:
        instance.test_plot_prop_matches_reference_0()

    message = str(exc.value)
    assert prop in message
    assert "does not support" in message
    # Every currently supported prop should be listed so the grader
    # knows what to pick from.
    for supported in SUPPORTED_PROPS:
        assert supported in message


def test_supported_octave_prop_passes_the_guard(fix_syspath):
    """Sanity check: a supported prop must NOT trip the guard.

    We can't run the full test without Octave, but we can assert that
    the guard branch is skipped and execution proceeds into ``RefUser``
    creation (which then fails with the runtime's "sub.m not found"
    hint on hosts without an actual ``ref.m``).
    """

    options = Options(
        sub_module="sub",
        ref_module="ref",
        obj_name="do_stuff",
        weight=1,
        language="octave",
        prop="title",
    )
    built_class = build(options)
    instance = built_class(methodName="test_plot_prop_matches_reference_0")
    with pytest.raises(Exception) as exc:
        instance.test_plot_prop_matches_reference_0()

    message = str(exc.value)
    # The failure should come from the reference-file check, not from
    # the language guard.
    assert "does not support" not in message
