"""Test for presence of specified class."""

import inspect
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import options_to_params


def doc_func(func, num, param):
    """Return parameterized docstring when checking for the existence of a
    class.
    """

    o = param.args[0]

    docstring = (
        f"Check that class `{o.obj_name}` is defined in module `{o.sub_module}`."
    )

    return docstring


def build(the_options):
    """Build the test class."""
    the_params = options_to_params(the_options)

    class TestClassIsDefined(unittest.TestCase):
        """A class for class presence tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_class_is_defined(self, options):
            """Check that sub_module defines the class."""

            o = options

            if o.init:
                o.init(self, o)

            obj = Importer.import_obj(self, o.sub_module, o)

            message = (
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

            if not inspect.isclass(obj):
                self.fail(message)

            self.set_score(self, o.weight)

    return TestClassIsDefined
