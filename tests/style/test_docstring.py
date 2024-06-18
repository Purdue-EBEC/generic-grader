import unittest

import pytest

from generic_grader.style.docstring import build


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(submission=None, reference=None)


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
    assert hasattr(built_instance, "setUp")
    assert hasattr(built_instance, "test_docstring_module")
    assert hasattr(built_instance, "test_docstring_author")
    assert hasattr(built_instance, "test_docstring_assignment_name")
    assert hasattr(built_instance, "test_docstring_date")
    assert hasattr(built_instance, "test_docstring_desc")
    assert hasattr(built_instance, "test_docstring_contributors")
    assert hasattr(built_instance, "test_docstring_integrity")


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

miss_assignment_name = "Assignment: 00.1"
inc_assignment_name = "Assignment: 00.1 - A"
wrong_assignment_name = "Assignment: 00.1 - Road Trip"
comp_assignment_name = "Assignment: 00.1 - Hello User"

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
multi_contri = """Contributors:
    Test1, test1@purdue.edu
    Test2, test2@purdue.edu
    Test3, test3@purdue.edu
    Test4, test4@purdue.edu
    Test5, test5@purdue.edu
    My contributor(s) helped me:
    [X] understand the assignment expectations without
        telling me how they will approach it.
    [X] understand different ways to think about a solution
        without helping me plan my solution.
    [X] think through the meaning of a specific error or
        bug present in my code without looking at my code.
    Note that if you helped somebody else with their code, you
    have to list that person as a contributor."""

miss_acdmc_int = ""
modified_acdmc_int = """Academic Integrity Statement:
    I have used source code obtained from any unauthorized
    source, either modified or unmodified; I provided
    another student access to my code.  The project I am
    submitting is not my own original work."""
comp_acdmc_int = """Academic Integrity Statement:
    I have not used source code obtained from any unauthorized
    source, either modified or unmodified; nor have I provided
    another student access to my code.  The project I am
    submitting is my own original work."""

# Test a file with
#   - Parse error for each test
#   - Module level docstring absent
#   - Missing author
#   - Incomplete author name (1 character)
#   - Missing author email
#   - Missing assignment name
#   - Incomplete assignment name
#   - Wrong assignment name
#   - Missing date
#   - Missing description
#   - Description too short
#   - Description too long
#   - Missing contributors
#   - Multiple contributors
#   - Missing academic integrity statement
#   - Modified academic integrity statement
#   - All components present for each test

cases = [
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_module",
    },
    {
        "submission": "",
        "reference": comp,
        "result": AssertionError,
        "message": "The program's docstring was not found",
        "method": "test_docstring_module",
    },
    {
        "submission": comp,
        "reference": comp,
        "result": "pass",
        "message": "Docstring is valid",
        "method": "test_docstring_module",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_author",
    },
    {
        "submission": f'''"""{miss_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The author's name was not found",
        "method": "test_docstring_author",
    },
    {
        "submission": f'''"""{inc_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The author's name was not found",
        "method": "test_docstring_author",
    },
    {
        "submission": f'''"""{miss_email}
                            {comp_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The author's email address was not found",
        "method": "test_docstring_author",
    },
    {
        "submission": comp,
        "reference": comp,
        "result": "pass",
        "message": "Docstring is valid",
        "method": "test_docstring_author",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_assignment_name",
    },
    {
        "submission": f'''"""{comp_auth}
                            {miss_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The assignment's name was not found.",
        "method": "test_docstring_assignment_name",
    },
    {
        "submission": f'''"""{comp_auth}
                            {inc_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The assignment name doesn't match the required name",
        "method": "test_docstring_assignment_name",
    },
    {
        "submission": f'''"""{comp_auth}
                            {wrong_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The assignment name doesn't match the required name",
        "method": "test_docstring_assignment_name",
    },
    {
        "submission": comp,
        "reference": comp,
        "result": "pass",
        "message": "Docstring is valid",
        "method": "test_docstring_assignment_name",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_date",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assignment_name}
                            {miss_date}
                            {comp_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": " The program's date was not found.",
        "method": "test_docstring_date",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_desc",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {miss_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The program's description was not found.",
        "method": "test_docstring_desc",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {short_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The program's description is too short.",
        "method": "test_docstring_desc",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {long_desc}
                            {comp_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The program's description is too long.",
        "method": "test_docstring_desc",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_contributors",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {miss_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The program contributors section is missing or too short.",
        "method": "test_docstring_contributors",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {multi_contri}
                            {comp_acdmc_int}"""''',
        "reference": comp,
        "result": "pass",
        "message": "Docstring is valid",
        "method": "test_docstring_contributors",
    },
    {
        "submission": comp,
        "reference": comp,
        "result": "pass",
        "message": "Docstring is valid",
        "method": "test_docstring_contributors",
    },
    {
        "submission": parse_err,
        "reference": comp,
        "result": AssertionError,
        "message": "Error while parsing",
        "method": "test_docstring_integrity",
    },
    {
        "submission": f'''"""{comp_auth}
                            {comp_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {miss_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The Academic Integrity Statement is missing or modified.",
        "method": "test_docstring_integrity",
    },
    {
        "submission": f'''"""{comp_auth}
                            {inc_assignment_name}
                            {comp_date}
                            {comp_desc}
                            {comp_contri}
                            {modified_acdmc_int}"""''',
        "reference": comp,
        "result": AssertionError,
        "message": "The Academic Integrity Statement is missing or modified.",
        "method": "test_docstring_integrity",
    },
    {
        "submission": comp,
        "reference": comp,
        "result": "pass",
        "message": "Docstring is valid",
        "method": "test_docstring_integrity",
    },
]


@pytest.fixture(params=cases)
def case_test_method(request, tmp_path, monkeypatch):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    file_path = tmp_path / "hello_user.py"
    submission = file_path.name
    file_path.write_text(case["submission"])
    file_path = tmp_path / "reference.py"
    reference = file_path.name
    file_path.write_text(case["reference"])
    monkeypatch.chdir(tmp_path)

    built_class = build(submission, reference)
    built_instance = built_class()
    test_method = getattr(built_instance, case["method"])
    custom_setup_method = getattr(built_instance, "setUp")

    return case, test_method, custom_setup_method


def test_docstring(case_test_method):
    """Test docstring of test_submitted_files function."""
    case, test_method, custom_setup_method = case_test_method

    if case["result"] == "pass":
        custom_setup_method()
        test_method()  # should not raise an error

    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            custom_setup_method()
            test_method()
        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
