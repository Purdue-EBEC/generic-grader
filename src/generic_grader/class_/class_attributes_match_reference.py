"""Test attributes of a class."""

import inspect
import textwrap
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import options_to_params


def doc_func(func, num, param):
    """Return parameterized docstring when checking for class attributes."""

    o = param.args[0]

    docstring = (
        f"Check that `{o.obj_name}` class attribute names and types"
        " match the reference."
    )

    return docstring


def build(the_options):
    the_params = options_to_params(the_options)

    class TestClassAttributesMatchReference(unittest.TestCase):
        """A class for class attribute presence tests."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_class_attributes_match_reference(self, options):
            """Check that the class attributes defined in the sub_module match
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

            # Construct sets of the submitted and reference class attributes that
            # are not in default object.
            sub_class = Importer.import_obj(self, o.sub_module, o)
            sub_attrs = (
                set(
                    (type(value).__name__, name)
                    for (name, value) in inspect.getmembers(sub_class)
                )
                - nul_attrs
            )

            ref_class = Importer.import_obj(self, o.ref_module, o)
            ref_attrs = (
                set(
                    (type(value).__name__, name)
                    for (name, value) in inspect.getmembers(ref_class)
                )
                - nul_attrs
            )

            missing_attrs = sorted(ref_attrs - sub_attrs)
            extra_attrs = sorted(sub_attrs - ref_attrs)

            # Construct an error message including lists of missing and extra attributes.
            message = (
                "\n"
                + self.wrapper.fill(
                    f"The `{o.obj_name}` class has incorrect attributes."
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
                    f"Define each attribute or method of your `{o.obj_name}` class"
                    f" inside the class definition (i.e. in the block after"
                    f" `class {o.obj_name}():`)." + (o.hint and f"  {o.hint}" or "")
                )
            )

            self.maxDiff = None
            if missing_attrs or extra_attrs:
                self.fail(message)

            self.set_score(self, options.weight)

    return TestClassAttributesMatchReference
