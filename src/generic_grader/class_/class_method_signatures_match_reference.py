"""Test signatures of class methods."""

import difflib
import inspect
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import options_to_params


def doc_func(func, num, param):
    """Return parameterized docstring when checking for the signatures of
    methods in a class.
    """

    o = param.args[0]

    docstring = f"Check the signature of each method in the `{o.obj_name}` class."

    return docstring


def build(the_options):
    """Create the test class for checking the signatures of methods in a class."""

    the_params = options_to_params(the_options)

    class TestClassMethodSignaturesMatchReference(unittest.TestCase):
        """A class for class method signature tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_class_method_signatures_match_reference(self, options):
            """Check that the signatures of methods defined in a class match
            those defined in the reference.
            """

            o = options

            sub_class = Importer.import_obj(self, o.sub_module, o)
            sub_funcs = dict(inspect.getmembers(sub_class, inspect.isfunction))

            ref_class = Importer.import_obj(self, o.ref_module, o)
            ref_funcs = dict(inspect.getmembers(ref_class, inspect.isfunction))

            message = ""
            for func_name in ref_funcs.keys():
                try:
                    ref_sig = f"{func_name}{inspect.signature(ref_funcs[func_name])}\n"
                    sub_sig = f"{func_name}{inspect.signature(sub_funcs[func_name])}\n"
                except KeyError:
                    # The method is missing from the submitted class.
                    message += f"\n{o.obj_name}.{func_name}:\n" + self.wrapper.fill(
                        f"The `{o.obj_name}` class in your `{o.sub_module}`"
                        f" module is missing a method named `{func_name}`."
                        f" Define the `{func_name}` method inside of your"
                        f" `{o.obj_name}` class using a `def` statement"
                        f" (e.g. `def {func_name}(self, ...):`)."
                    )
                    continue

                # Check if signatures differ.
                if ref_sig != sub_sig:
                    message += (
                        f"\n{o.obj_name}.{func_name}:\n"
                        + self.wrapper.fill(
                            f"The signature of your `{o.obj_name}.{func_name}`"
                            " method differs from the reference."
                            + (o.hint and f"  {o.hint}" or "")
                        )
                        + "\n\n"
                        + "".join(difflib.ndiff([sub_sig], [ref_sig]))
                    )

            if message:
                self.fail(message)

            self.set_score(self, o.weight)

    return TestClassMethodSignaturesMatchReference
