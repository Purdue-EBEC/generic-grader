import unittest

from generic_grader.output import output_lines_match_reference
from generic_grader.style import comments, docstring, program_length
from generic_grader.utils.file_set_up import file_set_up
from generic_grader.utils.options import Options

comment_cases = [
    {
        "entries": ("Tim the Enchanter",),
    },
    {
        "entries": ("King Arthur",),
    },
]

test_01_TestCommentLength = comments.build(
    Options(
        weight=3,
        sub_module="hello_user",
        hint="Check the volume of comments in your code.",
        entries=case["entries"],
    )
    for case in comment_cases
)

test_02_TestDocstring = docstring.build(Options(sub_module="hello_user"))

test_03_TestProgramLength = program_length.build(Options(sub_module="hello_user"))

test_04_TestOutput = output_lines_match_reference.build(
    Options(
        weight=1,
        obj_name="main",
        sub_module="hello_user",
        ref_module="reference",
        entries=("AJ",),
    ),
)


if __name__ == "__main__":
    with file_set_up(Options(required_files=("hello_user*.py",))):
        unittest.main()
