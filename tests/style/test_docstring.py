import unittest

import pytest
from parameterized import param

from generic_grader.style.docstring import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    o = Options()
    the_params = param(o)
    return build(the_params)


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_style_docstring_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_style_docstring_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestDocstring"


def test_style_docstring_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_style_docstring_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_docstring_module_0")
    assert hasattr(built_instance, "test_docstring_author_0")
    assert hasattr(built_instance, "test_docstring_assgnmt_name_0")
    assert hasattr(built_instance, "test_docstring_date_0")
    assert hasattr(built_instance, "test_docstring_desc_0")
    assert hasattr(built_instance, "test_docstring_contributors_0")
    assert hasattr(built_instance, "test_docstring_integrity_0")


# Test a file with
#   - Module level docstring absent
#   - Author absent
#   - Assignment name absent
#   - Assignment date absent
#   - Description too short* - yet to add
#   - Description too long* - yet to add
#   - Contributors absent
#   - Academic Integrity statement absent
#   - All components present

comp = '''"""
Author: John Cole, jhcole@purdue.edu
Assignment: 00.1 - Hello User
Date: 2022/01/09

Description:
    This program get the user's name and then displays a message.

Contributors:
    Name, login@purdue.edu [repeat for each]

My contributor(s) helped me:
    [ ] understand the assignment expectations without
        telling me how they will approach it.
    [ ] understand different ways to think about a solution
        without helping me plan my solution.
    [ ] think through the meaning of a specific error or
        bug present in my code without looking at my code.
    Note that if you helped somebody else with their code, you
    have to list that person as a contributor.

Academic Integrity Statement:
    I have not used source code obtained from any unauthorized
    source, either modified or unmodified; nor have I provided
    another student access to my code.  The project I am
    submitting is my own original work.
"""'''
parse_err = "print("

miss_auth = "Author:"
inc_auth = "Author: A"
miss_email = "Author: John Cole"
comp_auth = "Author: John Cole, jhcole@purdue.edu"

miss_assgnmt_name = "Assignment: 00.1"
inc_assgnmt_name = "Assignment: 00.1 - A"
wrong_assgnmt_name = "Assignment: 00.1 - Road Trip"
comp_assgnmt_name = "Assignment: 00.1 - Hello User"

miss_date = "Date:"
comp_date = "Date: 2022/01/09"

miss_desc = "Description:"
short_desc = "Description:\nshort"
long_desc = "Description:\n" + "\nlonglonglonglong" * 30
comp_desc = """Description:
    This program get the user's name and then displays a message."""

miss_contri = "Contributors:"
comp_contri = """Contributors:
    Name, login@purdue.edu [repeat for each]
    My contributor(s) helped me:
    [ ] understand the assignment expectations without
        telling me how they will approach it.
    [ ] understand different ways to think about a solution
        without helping me plan my solution.
    [ ] think through the meaning of a specific error or
        bug present in my code without looking at my code.
    Note that if you helped somebody else with their code, you
    have to list that person as a contributor."""

miss_acdmc_int = ""
modified_acdmc_int = """Academic Integrity Statement:
    I have used source code obtained from any unauthorized
    source, either modified or unmodified; nor have I provided
    another student access to my code.  The project I am
    submitting is my own original work."""
comp_acdmc_int = """Academic Integrity Statement:
    I have not used source code obtained from any unauthorized
    source, either modified or unmodified; nor have I provided
    another student access to my code.  The project I am
    submitting is my own original work."""


cases = [
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_module_0",
    },
    {
        "submission": "",
        "reference": comp,
        "result": AssertionError,
        "message": "The program's docstring was not found",
        "method": "test_docstring_module_0",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_author_0",
    },
    {
        "submission": f'''"""{inc_auth}
                            {comp_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The author's name was not found",
        "method": "test_docstring_author_0",
    },
    {
        "submission": f'''"""{inc_auth}
                            {comp_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The author's name was not found",
        "method": "test_docstring_author_0",
    },
    {
        "submission": f'''"""{miss_email}
                            {comp_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The author's email address was not found",
        "method": "test_docstring_author_0",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_assgnmt_name_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {miss_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The assignment's name was not found.",
        "method": "test_docstring_assgnmt_name_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {inc_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The assignment name doesn't match the required name",
        "method": "test_docstring_assgnmt_name_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {wrong_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The assignment name doesn't match the required name",
        "method": "test_docstring_assgnmt_name_0",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_date_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assgnmt_name}
                            {miss_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": " The program's date was not found.",
        "method": "test_docstring_date_0",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_desc_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assgnmt_name}
                            {comp_date}
                            {miss_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The program's description was not found.",
        "method": "test_docstring_desc_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assgnmt_name}
                            {comp_date}
                            {short_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The program's description is too short.",
        "method": "test_docstring_desc_0",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_contributors_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {miss_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The program contributors section is missing or too short.",
        "method": "test_docstring_contributors_0",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_integrity_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {miss_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The Academic Integrity Statement is missing or modified.",
        "method": "test_docstring_integrity_0",
    },
    {
        "submission": f'''"""{comp_auth}
                            {inc_assgnmt_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {modified_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The Academic Integrity Statement is missing or modified.",
        "method": "test_docstring_integrity_0",
    },
    {
        "submission": comp,
        "reference": comp,
        "result": "pass",
        "message": "Docstring is valid",
        "method": "test_docstring_integrity_0",
    },
]

# Make a table for all possible tests

# Make the value of submission key to an entire submission
# Try taking thing in an out to test if it works


@pytest.fixture(params=cases)
def case_test_method(request, tmp_path, monkeypatch):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    file_path = tmp_path / "hello_user.py"
    file_path.write_text(case["submission"])
    file_path = tmp_path / "reference.py"
    file_path.write_text(case["reference"])
    monkeypatch.chdir(tmp_path)

    the_params = [
        param(
            Options(
                sub_module="hello_user",
                ref_module="reference",
            ),
        )
    ]
    built_class = build(the_params)
    built_instance = built_class()
    test_method = getattr(built_instance, case["method"])

    return case, test_method


def test_docstring(case_test_method):
    """Test docstring of test_submitted_files function."""
    case, test_method = case_test_method

    if case["result"] == "pass":
        test_method()  # should not raise an error
    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            test_method()
        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
