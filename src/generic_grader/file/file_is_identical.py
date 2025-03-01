"""Test the binary content of a file."""

import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str, oxford_list
from generic_grader.utils.options import Options, options_to_params
from generic_grader.utils.reference_test import reference_test


def doc_func(func, num, param):
    """Return parameterized docstring when checking the binary content of a file."""

    o = param.args[0]

    filenames = [f"`{filename}`" for filename in o.filenames]
    file_s = "file" if len(filenames) == 1 else "files"
    file_list_str = f"{file_s} {oxford_list(filenames)}"
    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Checks the data written to the {file_list_str}"
        f" from your `{o.sub_module}.{o.obj_name}` function"
        f" when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}." or ".")
    )

    return docstring


def build(options):
    """A class for file content tests."""

    the_params = options_to_params(options)

    class TestFileIsIdentical(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_file_is_identical(self, options: Options):
            """Check for the expected data in a file."""

            o = options

            if not o.filenames:
                raise ValueError(
                    "There are no files to check."
                    "  This test requires filenames to be specified."
                )

            # Get the actual and expected values.
            ref_files, sub_files = [], []
            for filename in o.filenames:
                with open(f"ref_{filename}", "rb") as fo:
                    ref_files.append(fo.read())
                with open(f"sub_{filename}", "rb") as fo:
                    sub_files.append(fo.read())

            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            for ref_file, sub_file, filename in zip(ref_files, sub_files, o.filenames):
                # Test the result.
                message = str(
                    f"\nThe data in `{filename}` does not match the expected data."
                    f"  Double check the data written to the file {filename}"
                    f" by your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (o.hint and f" {o.hint}" or "")
                )
                actual = sub_file
                expected = ref_file

                self.assertEqual(actual, expected, msg=message)
            self.set_score(self, options.weight)

    return TestFileIsIdentical
