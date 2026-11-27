"""Python runtime — preserves the legacy in-process execution model.

Before the runtime abstraction landed,
:mod:`generic_grader.utils.user` called
:meth:`generic_grader.utils.importer.Importer.import_obj` directly to
load the target and then invoked it inside
:func:`generic_grader.utils.patches.custom_stack` to apply the Layer-1
security patches, resource limits, and stdout redirection.

This module packages exactly that behavior behind the
:class:`~generic_grader.runtimes.base.Runtime` protocol so that a
non-Python runtime (currently :mod:`generic_grader.runtimes.octave`) can
be selected via ``Options.language`` without changing any of the
existing test types.  Nothing about the Python path is *new* here — the
error messages, patch stack, and resource limits all still come from
:func:`custom_stack` and :class:`Importer`.  The seam between "resolve
the target" and "run the target" is now explicit, which lets other
runtimes plug in without reproducing the Python security-patch story.
"""

from __future__ import annotations

from copy import deepcopy
from unittest import TestCase

from attrs import evolve

from generic_grader.runtimes.base import RuntimeResult
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import Options
from generic_grader.utils.patches import custom_stack


class PythonRuntime:
    """Runtime backed by the current in-process Python execution model."""

    name = "Python"

    def resolve(self, test: TestCase, options: Options, module: str):
        """Import ``options.obj_name`` from ``module`` via
        :class:`Importer`.

        The existing student-facing error messages
        (``AttributeError`` → "Unable to import ...",
        ``ModuleNotFoundError`` → "Unable to import ...", accidental
        top-level ``input()`` → "Stuck at call to input()", ...) are
        preserved verbatim because we simply delegate to the same
        importer the legacy code used.
        """
        return Importer.import_obj(test, module, options)

    def run(
        self,
        options: Options,
        handle,
        log,
        entries,
    ) -> RuntimeResult:
        """Invoke the imported callable inside :func:`custom_stack`.

        ``handle`` is whatever :meth:`resolve` returned (the imported
        object).  The caller (``__User__.call_obj``) has already added
        ``sys.stdout → log`` and ``builtins.input → responder`` to
        ``options.patches``, so we just apply the full custom stack
        and call the object.  Any exception propagates up to
        ``call_obj``, which owns the student-facing error formatting.
        """
        # `entries` is currently ignored by the Python runtime because
        # simulated input arrives via the ``builtins.input`` patch on
        # ``options.patches`` (installed by the caller).  Non-Python
        # runtimes that pipe stdin will consume it directly.
        del entries
        stack_o = evolve(options, patches=options.patches)
        with custom_stack(stack_o):
            returned = handle(*deepcopy(options.args), **deepcopy(options.kwargs))
        return RuntimeResult(returned_values=returned)


__all__ = ("PythonRuntime",)
