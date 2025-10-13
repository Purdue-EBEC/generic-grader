import unittest

import pytest

from generic_grader.function.function_return_values_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_function_return_values_match_reference_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_function_return_values_match_reference_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFunctionReturnValuesMatchReference"


def test_function_return_values_match_reference_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_function_return_values_match_reference_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_function_return_values_match_reference_0")


# Cases Tested:
# 1. Correct returned value
# 2. Returned value is almost equal to expected value
# 3. Type difference in returned values
# 4. Value difference in returned values (int values)
# 5. Value difference in returned values (float values)


cases = [
    {  # Correct returned value
        "submission": "def test_function():\n    return [True, 1, 'abcd', [1,2]]",
        "reference": "def test_function():\n    return [True, 1, 'abcd', [1,2]]",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    },
    {  # Returned value is almost equal to expected value
        "submission": "def test_function():\n    return 0.9999999999",
        "reference": "def test_function():\n    return 1.0",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    },
    {  # Type difference in returned values
        "submission": "def test_function():\n    return 1234",
        "reference": "def test_function():\n    return '1234'",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the type of the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as """
            """`test_function()` match the reference value(s)."""
        ),
    },
    {  # Value difference in returned values (int values)
        "submission": "def test_function():\n    return 12345",
        "reference": "def test_function():\n    return 1234",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as """
            """`test_function()` match the reference value(s)."""
        ),
    },
    {  # Value difference in returned values (float values)
        "submission": "def test_function():\n    return 12345.0",
        "reference": "def test_function():\n    return 1234.0",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as """
            """`test_function()` match the reference value(s)."""
        ),
    },
]


# Case: numpy arrays returned - equal arrays should pass
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.array([1,2,3])",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1,2,3])",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: numpy arrays returned - differing arrays should fail
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.array([1,2,4])",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1,2,3])",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: floating numpy arrays that are nearly equal should pass (use allclose)
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.0])",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.00000001])",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: floating numpy arrays that are not nearly equal should fail
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.0])",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.1])",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: type mismatch where reference returns a numpy array but submission returns a list
cases.append(
    {
        "submission": "def test_function():\n    return [1,2,3]",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1,2,3])",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the type of the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)


@pytest.fixture(params=cases)
def case_test_method(request, fix_syspath):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    file_path = fix_syspath / f"{case['options'].sub_module}.py"
    file_path.write_text(case["submission"])
    file_path = fix_syspath / f"{case['options'].ref_module}.py"
    file_path.write_text(case["reference"])

    built_class = build(case["options"])
    built_instance = built_class(
        methodName="test_function_return_values_match_reference_0"
    )
    test_method = built_instance.test_function_return_values_match_reference_0

    return case, test_method


def test_function_return_values_match_reference(case_test_method):
    """Test response of test_submitted_files function."""
    case, test_method = case_test_method

    if case["result"] == "pass":
        test_method()  # should not raise an error
        assert test_method.__score__ == case["options"].weight
        assert test_method.__doc__ == case["doc_func_test_string"]

    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            test_method()
        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
        assert test_method.__doc__ == case["doc_func_test_string"]
        assert test_method.__score__ == 0


def test_handles_missing_numpy_import(monkeypatch, fix_syspath):
    """If numpy cannot be imported, code should fall back to non-numpy logic."""
    # Arrange: submission and reference return plain lists (no numpy needed)
    submission = "def test_function():\n    return [1,2,3]"
    reference = "def test_function():\n    return [1,2,3]"
    file_path = fix_syspath / "submission.py"
    file_path.write_text(submission)
    file_path = fix_syspath / "reference.py"
    file_path.write_text(reference)

    options = Options(
        obj_name="test_function",
        sub_module="submission",
        ref_module="reference",
        weight=1,
    )

    built_class = build(options)
    built_instance = built_class(
        methodName="test_function_return_values_match_reference_0"
    )
    test_method = built_instance.test_function_return_values_match_reference_0

    # Force import of numpy to fail inside the test method
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("no numpy")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    # Act / Assert: should run and pass (no numpy required for these returns)
    test_method()
    assert test_method.__score__ == options.weight


def test_numpy_comparison_exception_is_propagated(monkeypatch, fix_syspath):
    """If numpy comparison raises, the exception should propagate (current behavior)."""
    # Arrange: submission and reference return numpy arrays
    submission = (
        "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.0])"
    )
    reference = (
        "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.0])"
    )
    file_path = fix_syspath / "submission.py"
    file_path.write_text(submission)
    file_path = fix_syspath / "reference.py"
    file_path.write_text(reference)

    options = Options(
        obj_name="test_function",
        sub_module="submission",
        ref_module="reference",
        weight=1,
    )

    built_class = build(options)
    built_instance = built_class(
        methodName="test_function_return_values_match_reference_0"
    )
    test_method = built_instance.test_function_return_values_match_reference_0

    # Monkeypatch numpy.allclose to raise an error to hit the comparison except branch
    import numpy as np

    def raise_error(*args, **kwargs):
        raise RuntimeError("comparison failed")

    monkeypatch.setattr(np, "allclose", raise_error)

    # Act / Assert: the RuntimeError should be raised when running the test method
    with pytest.raises(RuntimeError):
        test_method()
