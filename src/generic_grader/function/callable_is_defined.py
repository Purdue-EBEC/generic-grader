"""Test for presence of specified callable."""

import inspect
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import ObjectType, Options, options_to_params


def doc_func(func, num, param):
    """Return parameterized docstring when checking for the existence of a
    class.
    """

    o = param.args[0]

    docstring = (
        f"Check that callable `{o.obj_name}` is defined in module `{o.sub_module}`."
    )

    return docstring


def build(the_options):
    """Build the test class."""
    the_params = options_to_params(the_options)

    class TestCallableIsDefined(unittest.TestCase):
        """A class for callable presence tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_callable_is_defined(self, options: Options):
            """Check that sub_module defines the callable."""

            o = options

            if o.init:
                o.init(self, o)
            # If the object is a function, this will raise an error if it is undefined
            obj = Importer.import_obj(self, o.sub_module, o)

            class_message = (
                "\n"
                + self.wrapper.fill(f"The object `{o.obj_name}` is not a class.")
                + "\n\nHint:\n"
                + self.wrapper.fill(
                    f"Define the `{o.obj_name}` class in your `{o.sub_module}`"
                    f" module using a `class` statement (e.g. `class {o.obj_name}():`)."
                    "  Also, make sure your class definition is not inside"
                    " of any other block." + (o.hint and f"  {o.hint}" or "")
                )
            )
            function_message = (
                "\n"
                + self.wrapper.fill(f"The object `{o.obj_name}` is not a function.")
                + "\n\nHint:\n"
                + self.wrapper.fill(
                    f"Define the `{o.obj_name}` function in your `{o.sub_module}`"
                    f" module using a `def` statement (e.g. `def {o.obj_name}():`)."
                    "  Also, make sure your function definition is not inside"
                    " of any other block." + (o.hint and f"  {o.hint}" or "")
                )
            )
            if o.object_type is ObjectType.CLASS and not inspect.isclass(obj):
                self.fail(class_message)
            elif o.object_type is ObjectType.FUNCTION and not inspect.isfunction(obj):
                self.fail(function_message)

            self.set_score(self, o.weight)

    return TestCallableIsDefined
