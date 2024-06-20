"""Handle importing objects from student code."""

import textwrap
import unittest
from unittest.mock import patch

from generic_grader.utils.exceptions import handle_error


class Importer:
    """A class for object import handling."""

    wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

    class InputError(Exception):
        """Custom Exception type."""

    @classmethod
    def raise_input_error(cls):
        """Raise our custom exception."""
        raise cls.InputError()

    @classmethod
    def import_obj(cls, test: unittest.TestCase, module: str, obj_name: str):
        """Import and return the requested object from module. Special
        handling is applied to catch input() statements and missing
        objects."""

        imp_obj = None
        try:
            fail_msg = False
            # Override input() to raise an exception if it gets called.
            with patch(
                "builtins.input", lambda *args, **kwargs: cls.raise_input_error()
            ):
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

        except Exception as e:
            fail_msg = handle_error(e, f"Error while importing `{obj_name}`.")
            test.failureException = type(e)

        # Fail outside of the except block
        # so that AssertionError(s) will be handled properly.
        if fail_msg:
            test.fail("\n" + fail_msg)

        return imp_obj
