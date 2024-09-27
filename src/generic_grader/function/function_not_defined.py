"""Test for absence of specified functions."""

import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.options import options_to_params
from generic_grader.utils.user import SubUser


def doc_func(func, num, param):
    """Return parameterized docstring when checking for the existence of a
    function.
    """

    o = param.args[0]

    docstring = f"Check that `{o.obj_name}` is NOT defined in module `{o.sub_module}`."

    return docstring


def build(the_options):
    the_params = options_to_params(the_options)

    class TestFunctionNotDefined(unittest.TestCase):
        """A class for function absence tests."""

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_function_not_defined(self, options):
            """Check that sub_module does not have its own obj_name."""

            o = options

            msg = None
            try:
                self.student_user = SubUser(self, o)
            except (ImportError, AttributeError):
                pass  # The expected result.
            else:
                msg = (
                    f"The definition of your `{o.obj_name}` function "
                    f"should not be within your `{o.sub_module}` module."
                    + (o.hint and f" {o.hint}")
                )

            if msg:
                self.fail(msg)

            self.set_score(self, o.weight)

    return TestFunctionNotDefined
