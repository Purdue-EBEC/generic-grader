"""Guard against interactive matplotlib backends in the test suite.

The grader runs student code in-process under a 1-second time limit.  If the
test suite uses an interactive backend (e.g. Tk), the first figure creation
pays a one-time ``tk.Tk(...)`` initialization cost that can exceed the limit
and produce a spurious ``UserTimeoutError`` (see issue #205).
``generic_grader`` sets ``MPLBACKEND=Agg`` at import time for the runtime, and
``tests/conftest.py`` does the same for the test suite; these tests ensure both
settings stay in effect.
"""

import os
import subprocess
import sys

import matplotlib


def _non_interactive_backends():
    """Return the set of non-interactive backend names.

    Uses the modern backend registry when available (matplotlib >= 3.9) and
    falls back to the deprecated ``rcsetup`` attribute on older versions.
    """
    try:
        from matplotlib.backends import BackendFilter, backend_registry
    except ImportError:  # pragma: no cover - matplotlib < 3.9
        from matplotlib import rcsetup

        return set(rcsetup.non_interactive_bk)
    return set(backend_registry.list_builtin(BackendFilter.NON_INTERACTIVE))


def test_matplotlib_backend_is_non_interactive():
    """The test suite must not use an interactive matplotlib backend."""
    backend = matplotlib.get_backend().lower()
    assert backend in _non_interactive_backends(), (
        f"matplotlib is using the interactive backend {backend!r}; the test"
        " suite must use a non-interactive backend to avoid the cold-start"
        " timeout described in issue #205."
    )


def test_generic_grader_import_selects_non_interactive_backend():
    """Importing `generic_grader` must request a non-interactive backend.

    Runs in a fresh interpreter without `MPLBACKEND`, mirroring an autograder,
    so the suite-level setting cannot mask a runtime regression.  The requested
    backend is checked rather than the resolved one because backend
    auto-selection falls back to Agg whenever no usable display is available.
    """
    env = {k: v for k, v in os.environ.items() if k != "MPLBACKEND"}
    code = (
        "import generic_grader, matplotlib;"
        " print(matplotlib.rcParams._get_backend_or_none())"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip().lower() in _non_interactive_backends()
