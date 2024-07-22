from parameterized import param

from generic_grader.file import file_set_up
from generic_grader.style import comments, docstring
from generic_grader.utils.options import Options

test_00_TestFileSetUp = file_set_up.build(
    [
        param(
            Options(
                weight=0,
                required_files=["hello_user*.py"],
            ),
        ),
    ]
)


comment_cases = [
    {
        "entries": ("Tim the Enchanter"),
    },
    {
        "entries": ("King Arthur"),
    },
]

test_01_TestCommentLength = comments.build(
    param(
        Options(
            weight=3,
            sub_module="hello_user",
            ref_module="tests/reference",
            hint="Check the volume of comments in your code.",
            entries=case["entries"],
        ),
    )
    for case in comment_cases
)


test_02_TestDocstring = docstring.build(
    submission="hello_user.py", reference="tests/reference.py"
)
