"""Handle importing objects from student code."""

import traceback
import unittest
from pathlib import Path

from attrs import evolve

from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.exceptions import (
    EndOfInputError,
    handle_error,
    safe_exception_type,
)
from generic_grader.utils.options import Options
from generic_grader.utils.patches import custom_stack

# Sentinel returned by `Importer.import_obj` when `Options.use_sandbox`
# is set.  In sandbox mode there is no live callable to return (the
# real object lives inside the worker process, which exits between
# import and call), but the existing `__User__.__init__` only needs a
# truthy attribute.  `__User__.call_obj` checks for this sentinel and
# delegates to the sandbox integration module.
SANDBOX_OBJ_SENTINEL = object()


class Importer:
    """A class for object import handling."""

    wrapper = get_wrapper()

    class InputError(Exception):
        """Custom Exception type."""

    @classmethod
    def raise_input_error(cls, *args, **kwargs):
        """Raise our custom exception."""
        raise cls.InputError()

    @classmethod
    def _import_location_hint(cls, e: BaseException):
        """Return a concise location hint for a failed import from traceback."""
        tb = traceback.extract_tb(e.__traceback__)
        if not tb:
            return None

        frame = tb[-1]
        for candidate in reversed(tb):
            if candidate.line and "import" in candidate.line:
                frame = candidate
                break

        line = (frame.line or "").strip()
        filename = Path(frame.filename).name
        if line:
            return (
                f"The error occurred in `{filename}` on line {frame.lineno}: "
                f"`{line}`."
            )
        return f"The error occurred in `{filename}` on line {frame.lineno}."

    @classmethod
    def import_obj(cls, test: unittest.TestCase, module: str, o: Options):
        """Import and return the requested object from module. Special
        handling is applied to catch input() statements and missing
        objects."""
        if o.use_sandbox:
            return cls._sandbox_import_obj(test, module, o)

        obj_name = o.obj_name

        imp_obj = None
        fail_msg = False
        try:
            stack_o = evolve(
                o,
                patches=(o.patches or [])
                + [{"args": ["builtins.input", cls.raise_input_error]}],
            )
            # Override input() to raise an exception if it gets called.
            with custom_stack(stack_o):
                # Try to import student's object
                imp_obj = getattr(__import__(module, fromlist=[obj_name]), obj_name)

        except AttributeError:
            # Handle exception due to module missing the object.
            fail_msg = (
                cls.wrapper.fill(f"Unable to import `{obj_name}`.")
                + "\n\nHint:\n"
                + cls.wrapper.fill(
                    f"Define `{obj_name}` in your `{module}` module, and make"
                    " sure its definition is not inside of any other block."
                )
            )
            test.failureException = AttributeError

        except cls.InputError:
            # Handle exception raised by call to input.
            fail_msg = (
                cls.wrapper.fill(
                    f"Stuck at call to `input()` while importing `{obj_name}`."
                )
                + "\n\nHint:\n"
                + cls.wrapper.fill(
                    "Avoid calling `input()` in the global scope "
                    "(i.e. outside of any function or other code block)."
                )
            )
            test.failureException = cls.InputError
        except ModuleNotFoundError as e:
            # Handle exception due to absent target module, reporting deepest error in chain.
            missing_name = e.name or module
            current_e: BaseException = e
            while True:
                next_e = current_e.__cause__ or current_e.__context__
                if next_e is None:
                    break
                current_e = next_e
                if isinstance(current_e, ModuleNotFoundError):
                    missing_name = current_e.name or missing_name

            if missing_name == module or module.startswith(missing_name + "."):
                hint = (
                    f"Make sure you have submitted a module named `{module}` and "
                    f"it contains the definition of `{obj_name}`."
                )
            else:
                hint = (
                    f"Your `{module}` module imports `{missing_name}`, but "
                    f"that module could not be found. `{missing_name}` may be "
                    f"imported directly by `{module}`, or by another module that "
                    f"`{module}` depends on. If it is your own module, make sure "
                    "that it is included in your submission. If it is not your own "
                    "module, that dependency may not be available in the autograder "
                    "environment."
                )
                location_hint = cls._import_location_hint(current_e)
                if location_hint:
                    hint += f" {location_hint}"

            test.failureException = ModuleNotFoundError
            fail_msg = (
                cls.wrapper.fill(f"Unable to import `{module}`.")
                + "\n\nHint:\n"
                + cls.wrapper.fill(hint)
            )
        except Exception as e:
            fail_msg = handle_error(e, f"Error while importing `{obj_name}`.")
            test.failureException = safe_exception_type(type(e))

        # Fail outside of the except block
        # so that AssertionError(s) will be handled properly.
        if fail_msg:
            test.fail("\n" + fail_msg)

        return imp_obj

    # ------------------------------------------------------------------
    # Sandbox path (Layer 3, gated on Options.use_sandbox)
    # ------------------------------------------------------------------

    @classmethod
    def _sandbox_import_obj(cls, test: unittest.TestCase, module: str, o: Options):
        """Sandbox-backed equivalent of `import_obj`.

        Runs an import-only probe through a fresh isolate worker.  The
        classifier turns the worker's structured outcome back into the
        same student-facing failure messages produced by the in-process
        path (above), so existing assignments don't need to change
        anything besides setting ``Options.use_sandbox=True``.
        """
        # Imported lazily so projects that never opt into the sandbox
        # don't pay the import cost for the runner / isolate machinery.
        from generic_grader.sandbox.integration import (
            classify_import_outcome,
            sandbox_import_obj,
        )

        obj_name = o.obj_name
        result = sandbox_import_obj(module, o)
        outcome = classify_import_outcome(result)
        if outcome is None:
            return SANDBOX_OBJ_SENTINEL

        fail_msg = cls._format_sandbox_import_failure(outcome, result, module, obj_name)
        test.failureException = outcome
        test.fail("\n" + fail_msg)

    @classmethod
    def _format_sandbox_import_failure(
        cls,
        outcome: type[BaseException],
        result,
        module: str,
        obj_name: str,
    ) -> str:
        """Render a sandbox import outcome as a student-facing failure message.

        Mirrors the classification branches in `import_obj`: AttributeError
        -> "unable to import obj", EndOfInputError -> "stuck at input",
        ModuleNotFoundError -> module-resolution hint, anything else
        -> generic handle_error-style traceback derived from the
        worker's exception chain.
        """
        if outcome is AttributeError:
            return (
                cls.wrapper.fill(f"Unable to import `{obj_name}`.")
                + "\n\nHint:\n"
                + cls.wrapper.fill(
                    f"Define `{obj_name}` in your `{module}` module, and make"
                    " sure its definition is not inside of any other block."
                )
            )
        if outcome is EndOfInputError:
            return (
                cls.wrapper.fill(
                    f"Stuck at call to `input()` while importing `{obj_name}`."
                )
                + "\n\nHint:\n"
                + cls.wrapper.fill(
                    "Avoid calling `input()` in the global scope "
                    "(i.e. outside of any function or other code block)."
                )
            )
        if outcome is ModuleNotFoundError:
            # We don't have a live traceback in the host process to
            # walk; rely on the worker's structured message to surface
            # the missing dependency name.  The legacy path's deeper
            # chain-walk is preserved by `_extract_missing_module` so
            # multi-step ``ImportError`` chains still produce the
            # correct hint.
            missing_name = cls._extract_missing_module(result, module)
            if missing_name == module or module.startswith(missing_name + "."):
                hint = (
                    f"Make sure you have submitted a module named `{module}` and "
                    f"it contains the definition of `{obj_name}`."
                )
            else:
                hint = (
                    f"Your `{module}` module imports `{missing_name}`, but "
                    f"that module could not be found. `{missing_name}` may be "
                    f"imported directly by `{module}`, or by another module that "
                    f"`{module}` depends on. If it is your own module, make sure "
                    "that it is included in your submission. If it is not your own "
                    "module, that dependency may not be available in the autograder "
                    "environment."
                )
            return (
                cls.wrapper.fill(f"Unable to import `{module}`.")
                + "\n\nHint:\n"
                + cls.wrapper.fill(hint)
            )

        # Generic fallback: build a traceback-style message from the
        # worker's structured exception chain.
        chain = result.exception or []
        head = chain[0] if chain else {"type": outcome.__name__, "message": ""}
        tb_text = head.get("traceback") or ""
        formatted = (
            ("Traceback (most recent call last):\n" + tb_text) if tb_text else ""
        ) + f"{head.get('type', outcome.__name__)}: {head.get('message', '')}\n"
        from generic_grader.utils.exceptions import indent

        return indent(f"Error while importing `{obj_name}`.\n\n" + formatted)

    @staticmethod
    def _extract_missing_module(result, module: str) -> str:
        """Pull the deepest missing module name out of a worker exception chain.

        The legacy path walks the live ``__cause__`` / ``__context__``
        chain and prefers the deepest ``ModuleNotFoundError.name``.  We
        approximate that by scanning the structured chain for messages
        of the form ``No module named 'X'`` (CPython's canonical text)
        and picking the deepest one.
        """
        import re

        missing = module
        pattern = re.compile(r"No module named '([^']+)'")
        for link in result.exception or []:
            if link.get("type") == "ModuleNotFoundError":
                match = pattern.search(link.get("message") or "")
                if match:
                    missing = match.group(1)
        return missing
