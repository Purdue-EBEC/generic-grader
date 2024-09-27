"""Test the set of functions called by another function."""

import unittest

from attrs import evolve
from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import make_call_str
from generic_grader.utils.math_utils import n_trials
from generic_grader.utils.options import options_to_params
from generic_grader.utils.user import SubUser


def doc_func(func, num, param):
    """Return parameterized docstring when checking function(s) called from
    within another function call.
    """

    o = param.args[0]

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check the randomness of the functions(s) called"
        f" from within function call `{call_str}`"
        f" in your `{o.sub_module}` module"
        + (o.entries and f" with entries={o.entries}." or ".")
    )

    return docstring


def build(the_options):
    the_params = options_to_params(the_options)

    class TestRandomFunctionCalls(unittest.TestCase):
        """A class for functionality tests."""

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_random_function_calls(self, options):
            """Check for extra or missing function calls."""

            o = options
            call_list = []
            # We need to create this local variables value here because eval does not have acess to values outside of its scope
            # and since the loop is technically its own scope we need to manually set locals.
            # We also need to use eval here because otherwise `func` does not get evaluated until it is called.
            local_variables = locals()

            if o.init:
                o.init()

            new_patches = [
                {
                    "args": [
                        func,
                        eval(
                            f'lambda *args, **kwargs: call_list.append("{func}")',
                            local_variables,
                        ),
                    ],
                    "kwargs": {"create": True},
                }
                for func in o.random_func_calls
            ]

            o = evolve(o, patches=((o.patches or []) + new_patches))

            self.student_user = SubUser(self, o)

            # Collect the set by repeated calls to the function
            actual_perms = set()
            for _ in range(n_trials(len(o.expected_perms), o.random_chance_tolerance)):
                self.student_user.call_obj()
                actual_perms.add(tuple(call_list))
                call_list.clear()

            msg = (
                "It does not appear that your functions are being called randomly.\n"
                "  Please ensure that you are calling the functions in a random order."
            )

            self.assertEqual(actual_perms, o.expected_perms, msg=msg)
            self.set_score(self, o.weight)

    return TestRandomFunctionCalls
