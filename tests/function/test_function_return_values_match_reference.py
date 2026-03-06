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

# Case: loose relative_tolerance allows arrays differing beyond default rtol to pass
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.05])",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.0])",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            relative_tolerance=0.1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: tight relative_tolerance rejects arrays within the default rtol
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.00000001])",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.0])",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            relative_tolerance=1e-10,
        ),
        "message": "Double check the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: loose absolute_tolerance allows arrays with a small absolute difference to pass
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.5])",
        "reference": "import numpy as np\ndef test_function():\n    return np.array([1.0,2.0,3.0])",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            relative_tolerance=0.0,
            absolute_tolerance=1.0,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: equal np.float64 scalars should pass
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.float64(3.0)",
        "reference": "import numpy as np\ndef test_function():\n    return np.float64(3.0)",
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

# Case: unequal np.float64 scalars should fail
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.float64(3.1)",
        "reference": "import numpy as np\ndef test_function():\n    return np.float64(3.0)",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "difference)",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: type mismatch where reference returns np.float64 but submission returns float
cases.append(
    {
        "submission": "def test_function():\n    return 3.0",
        "reference": "import numpy as np\ndef test_function():\n    return np.float64(3.0)",
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

# Case: loose relative_tolerance allows np.float64 scalars differing beyond default rtol to pass
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.float64(3.05)",
        "reference": "import numpy as np\ndef test_function():\n    return np.float64(3.0)",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            relative_tolerance=0.1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: tight relative_tolerance rejects np.float64 scalars within the default rtol
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.float64(3.00000001)",
        "reference": "import numpy as np\ndef test_function():\n    return np.float64(3.0)",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            relative_tolerance=1e-10,
        ),
        "message": "difference)",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: loose absolute_tolerance allows np.float64 scalars with a small absolute difference to pass
cases.append(
    {
        "submission": "import numpy as np\ndef test_function():\n    return np.float64(3.5)",
        "reference": "import numpy as np\ndef test_function():\n    return np.float64(3.0)",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            relative_tolerance=0.0,
            absolute_tolerance=1.0,
        ),
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


def test_large_diff_does_not_timeout(fix_syspath):
    """Test that comparing large differing return values completes quickly.

    When self.maxDiff is None, unittest's assertEqual calls difflib.ndiff
    on pprint.pformat() output, which has O(n^2) complexity and can hang
    for minutes on large data.  safe_assert_equal avoids this by falling
    back to a truncated representation for large values.
    """
    # Arrange: functions that return large dicts with every value different.
    submission = (
        "def test_function():\n"
        "    return {f'key_{i}': f'value_a_{i}' for i in range(500)}\n"
    )
    reference = (
        "def test_function():\n"
        "    return {f'key_{i}': f'value_b_{i}' for i in range(500)}\n"
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

    import time

    start = time.time()
    with pytest.raises(AssertionError) as exc_info:
        test_method()
    elapsed = time.time() - start

    # The comparison must complete in under 10 seconds.
    # Without the fix, a 500-key dict diff takes minutes.
    assert elapsed < 10, (
        f"assertEqual on large differing dicts took {elapsed:.1f}s; "
        f"expected < 10s.  Is maxDiff still None?"
    )

    # The error message should contain a truncated repr, not all 500 keys.
    message = str(exc_info.value)
    assert "..." in message, "Expected truncated repr with '...' for large values"
    assert "key_499" not in message, (
        "Expected repr to be truncated, but found the last key"
    )
