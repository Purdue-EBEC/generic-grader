import pytest
from parameterized import param

from generic_grader.utils.options import ImageOptions, Options, options_to_params


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
]


@pytest.mark.parametrize("case", typecheck_options)
def test_typecheck_options(case):
    """Test that the runtime error is raised."""
    with pytest.raises(ValueError) as exc_info:
        Options(**case["options"])
    assert str(exc_info.value) == case["error"]


def test_utils_image_options():
    """Test that ImageOptions can be instantiated."""
    assert ImageOptions()


typecheck_image_options = [
    {
        "options": {"init": "str"},
        "error": "`init` must be of type <class 'function'> or <class 'NoneType'>. Got <class 'str'> instead.",
    },
    {
        "options": {"obj_name": 0},
        "error": "`obj_name` must be of type <class 'str'>. Got <class 'int'> instead.",
    },
]


@pytest.mark.parametrize("case", typecheck_image_options)
def test_typecheck_image_options(case):
    """Test that the runtime error is raised."""
    with pytest.raises(ValueError) as exc_info:
        ImageOptions(**case["options"])
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
