"""Language-guard helper for Python-only test types.

Several test types -- the AST-based style checks, ``inspect``-based
class introspection, ``sys.settrace`` random-call sampling, the
``file_closed`` monkeypatch, and the OCR/pixel image tests -- have
fundamentally no Octave analogue.  If a grader author accidentally
sets ``language="octave"`` for one of them, the resulting error
tends to be a cryptic ``AttributeError`` deep inside a helper.

This module provides one small helper that raises a clear, uniform
failure via ``test.fail(...)`` before the Python-only machinery
runs.  Keeping the check in a dedicated module means all guarded
tests share the same error text and the guard has a single obvious
place to grow (e.g. if we later want to warn on a subset of props
rather than the whole test type).
"""

from __future__ import annotations

from generic_grader.utils.options import Options


def require_python_language(test, options: Options, test_type: str) -> None:
    """Fail *test* if *options* selects a non-Python language.

    Parameters
    ----------
    test:
        The active :class:`unittest.TestCase` -- used only for
        ``test.fail``.  Passing the test in (rather than raising a
        bare exception) keeps the failure inside the normal grading
        report so the student sees a helpful message rather than a
        traceback in their score.
    options:
        The per-test :class:`Options` instance.  Only
        ``options.language`` is consulted.
    test_type:
        Human-readable name of the calling test type, e.g.
        ``"function.function_not_defined"``.  Included verbatim in
        the failure message so operators can search for it.
    """

    language = getattr(options, "language", "python") or "python"
    if language == "python":
        return

    test.fail(
        f"The `{test_type}` test type is Python-only and cannot run "
        f'against language={language!r}.  Set `language="python"` '
        f"in Options, or remove this test from the Octave suite."
    )
