"""Language runtimes for generic-grader.

A *runtime* is the small adapter layer that knows how to (a) resolve the
student- and reference-supplied "module" for a given language and (b) run
an ``obj_name`` from it with the caller's ``args``, ``kwargs``, and
simulated stdin ``entries``, returning the produced stdout, any return
value, and any exception in a language-agnostic form.

Runtimes are registered in :data:`RUNTIMES` under the same string that
callers pass as ``Options.language``.  The default remains ``"python"``,
which preserves the pre-existing in-process behavior and its full set of
security patches.  A new ``"octave"`` runtime executes GNU Octave scripts
and functions via a hardened subprocess.

The runtime interface is intentionally minimal (see
:class:`generic_grader.runtimes.base.Runtime`) so that additional
languages can be plugged in later (e.g. C, R, Julia) without touching the
User/RefTest machinery.
"""

from __future__ import annotations

from generic_grader.runtimes.base import Runtime, RuntimeResult
from generic_grader.runtimes.octave import OctaveRuntime
from generic_grader.runtimes.python import PythonRuntime

# Registry consulted by Options.__attrs_post_init__ (to validate
# ``language``) and by __User__.__init__ (to look up the concrete
# runtime).  Keys must be lowercase to keep the validator's error message
# stable and to avoid surprising case-sensitivity for test authors.
RUNTIMES: dict[str, type[Runtime]] = {
    "python": PythonRuntime,
    "octave": OctaveRuntime,
}


def get_runtime(language: str) -> type[Runtime]:
    """Return the runtime class registered for ``language``.

    Options.__attrs_post_init__ already rejects unknown languages, so a
    ``KeyError`` here would indicate an internal misuse rather than a
    user-facing configuration error.
    """
    return RUNTIMES[language]


__all__ = ("RUNTIMES", "Runtime", "RuntimeResult", "get_runtime")
