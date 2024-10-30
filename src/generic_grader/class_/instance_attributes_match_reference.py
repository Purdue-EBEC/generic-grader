"""Test attributes of a class."""

import inspect
import textwrap
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test


def doc_func(func, num, param):
    """Return parameterized docstring when checking for instance attributes."""

    o = param.args[0]

    docstring = (
        f"Check that `{o.obj_name}` instance attribute names and types"
        " match the reference."
    )

    return docstring


def build(the_options):
    the_params = options_to_params(the_options)

    class TestInstanceAttributesMatchReference(unittest.TestCase):
        """A class for instance attribute presence tests."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_instance_attributes_match_reference(self, options):
            """Check that the instance attributes defined in the sub_module match
            those defined in the reference.
            """

            o = options

            # Construct the set of default object attributes.
            nul_attrs = set(
                (type(value).__name__, name)
                for (name, value) in inspect.getmembers(object)
            )
            # Ignore missing docstrings.
            nul_attrs.add(("NoneType", "__doc__"))

            # Construct sets of the submitted and reference instance attributes that
            # are not in default object.
            sub_instance = self.student_user.returned_values
            sub_attrs = (
                set(
                    (type(value).__name__, name)
                    for (name, value) in inspect.getmembers(sub_instance)
                )
                - nul_attrs
            )

            ref_instance = self.ref_user.returned_values
            ref_attrs = (
                set(
                    (type(value).__name__, name)
                    for (name, value) in inspect.getmembers(ref_instance)
                )
                - nul_attrs
            )

            missing_attrs = sorted(ref_attrs - sub_attrs)
            extra_attrs = sorted(sub_attrs - ref_attrs)

            # Construct an error message including lists of missing and extra attributes.
            message = (
                "\n"
                + self.wrapper.fill(
                    f"Instances of the `{o.obj_name}` class have incorrect attributes."
                )
                + (
                    (
                        "\n\nMissing Attributes:\n"
                        + "\n".join(f"  {attr[0]}: {attr[1]}" for attr in missing_attrs)
                    )
                    if missing_attrs
                    else ""
                )
                + (
                    (
                        "\n\nExtra Attributes:\n"
                        + "\n".join(f"  {attr[0]}: {attr[1]}" for attr in extra_attrs)
                    )
                    if extra_attrs
                    else ""
                )
                + "\n\nHint:\n"
                + self.wrapper.fill(
                    f"Define each method of your `{o.obj_name}` class inside the class"
                    f" definition (i.e. in the block after `class {o.obj_name}():`)."
                    "  Data attributes can be added to an instance through the class's"
                    " `__init__` method." + (o.hint and f"  {o.hint}" or "")
                )
            )

            self.maxDiff = None
            if missing_attrs or extra_attrs:
                self.fail(message)

            self.set_score(self, o.weight)

    return TestInstanceAttributesMatchReference
