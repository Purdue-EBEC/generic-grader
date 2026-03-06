import pytest
from parameterized import param

from generic_grader.utils.options import Options, options_to_params


def test_single_options_to_params():
    # Arrange
    single_option = Options()

    # Act
    the_params = options_to_params(single_option)

    # Assert
    assert the_params == [param(single_option)]


def test_multiple_options_to_params():
    # Arrange
    sequence_options = (
        Options(),
        Options(),
    )

    # Act
    the_params = options_to_params(sequence_options)

    # Assert
    assert the_params == [param(o) for o in sequence_options]


def test_utils_options():
    """Test that Options can be instantiated."""
    assert Options()


typecheck_options = [
    {
        "options": {"init": ""},
        "error": "`init` must be of type <class 'function'> or <class 'NoneType'>. Got <class 'str'> instead.",
    },
    {
        "options": {"patches": {}},
        "error": "`patches` must be of type <class 'list'>. Got <class 'dict'> instead.",
    },
    {
        "options": {"entries": ""},
        "error": "`entries` must be of type <class 'tuple'>. Got <class 'str'> instead.",
    },
    {
        "options": {"weight": "0"},
        "error": "`weight` must be of type int | float. Got <class 'str'> instead.",
    },
    {
        "options": {"mode": "unknown"},
        "error": "`mode` must be one of 'exactly', 'less than', 'more than', or 'approximately'.",
    },
]


@pytest.mark.parametrize("case", typecheck_options)
def test_typecheck_options(case):
    """Test that the runtime error is raised."""
    with pytest.raises(ValueError) as exc_info:
        Options(**case["options"])
    assert str(exc_info.value) == case["error"]


# Valid init functions (should not raise)
valid_init_cases = [
    lambda test, options: None,  # exactly 2 params
    lambda test, options, extra=None: None,  # 2 required + 1 optional
    lambda *args: None,  # variadic
    lambda test, *args: None,  # 1 + variadic
]


@pytest.mark.parametrize("init", valid_init_cases)
def test_valid_init_signature(init):
    """Test that valid init functions are accepted."""
    Options(init=init)  # should not raise


# Invalid init functions (should raise ValueError)
invalid_init_cases = [
    {
        "init": lambda: None,
        "error": "`init` must accept 2 positional arguments (test, options), but accepts 0.",
    },
    {
        "init": lambda x: None,
        "error": "`init` must accept 2 positional arguments (test, options), but accepts 1.",
    },
]


@pytest.mark.parametrize("case", invalid_init_cases)
def test_invalid_init_signature(case):
    """Test that init functions with wrong signature are rejected."""
    with pytest.raises(ValueError) as exc_info:
        Options(init=case["init"])
    assert str(exc_info.value) == case["error"]


duplicate_file_names = [
    {
        "options": {"filenames": ("a", "a")},
        "error": "Duplicate entries in filenames.",
    },
    {
        "options": {"required_files": ("a", "a")},
        "error": "Duplicate entries in required_files.",
    },
    {
        "options": {"ignored_files": ("a", "a")},
        "error": "Duplicate entries in ignored_files.",
    },
]


@pytest.mark.parametrize("case", duplicate_file_names)
def test_duplicate_file_names(case):
    """Test that the runtime error is raised."""
    with pytest.raises(ValueError) as exc_info:
        Options(**case["options"])
    assert str(exc_info.value) == case["error"]
