"""Handle importing objects from student code."""

import unittest

from attrs import evolve

from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.exceptions import handle_error, safe_exception_type
from generic_grader.utils.options import Options
from generic_grader.utils.patches import custom_stack


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
    def import_obj(cls, test: unittest.TestCase, module: str, o: Options):
        """Import and return the requested object from module. Special
        handling is applied to catch input() statements and missing
        objects."""
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
            current_e = e
            while True:
                next_e = current_e.__cause__ or current_e.__context__
                if next_e is None:
                    break
                current_e = next_e
                if isinstance(current_e, ModuleNotFoundError):
                    missing_name = current_e.name or missing_name

            if missing_name == module:
                hint = (
                    f"Make sure you have submitted a file named `{module}.py` and "
                    f"it contains the definition of `{obj_name}`."
                )
            else:
                hint = (
                    f"Your `{module}` module imports `{missing_name}`, but "
                    f"that module could not be found. `{missing_name}` may be "
                    f"imported directly by `{module}`, or by another module that "
                    f"`{module}` depends on. If it is your own module, include "
                    "the required file in your submission."
                )

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
