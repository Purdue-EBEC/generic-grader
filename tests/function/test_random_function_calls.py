import unittest
from itertools import permutations

import pytest

from generic_grader.function.random_function_calls import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(sub_module="sub", entries=(7,)))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_random_function_calls_build_class(built_class):
    """Test that the build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_random_function_calls_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestRandomFunctionCalls"


def test_random_function_calls_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_random_function_calls_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_random_function_calls_0")


def test_random_function_calls_docstring(built_instance):
    """Make sure the docstring is correct."""
    assert built_instance.test_random_function_calls_0.__doc__ == (
        "Check the randomness of the functions(s) called from within function call `main()` in your `sub` module with entries=(7,)."
    )


passing_cases = [
    {  # Check that it works as expected with mutiple functions
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=[f"sub.func{i}" for i in [3, 2, 1]],
            expected_perms=set(permutations([f"sub.func{i}" for i in [3, 2, 1]])),
        ),
        "file_text": "import random\ndef func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass\n\ndef main():\n    funcs = [func1, func2, func3]\n    random.shuffle(funcs)\n    for func in funcs:\n        func()\n",
    },
    {  # Check that it works as expected with a single function
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=["sub.func1"],
            expected_perms={("sub.func1",)},
        ),
        "file_text": "def func1():\n    pass\n\ndef main():\n    func1()\n",
    },
    {  # Check that it works as expected with two functions
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=["sub.func1", "sub.func2"],
            expected_perms={("sub.func1", "sub.func2"), ("sub.func2", "sub.func1")},
        ),
        "file_text": "import random\ndef func1():\n    pass\n\ndef func2():\n    pass\n\ndef main():\n    funcs = [func1, func2]\n    random.shuffle(funcs)\n    for func in funcs:\n        func()\n",
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing_random_function_calls(fix_syspath, case):
    """Test that the function calls are random test works."""
    # Setup
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["file_text"])
    # Create the test method
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_random_function_calls_0")
    test_method = built_instance.test_random_function_calls_0
    # Run the test method
    test_method()
    # Make sure the score is correct
    assert test_method.__score__ == case["options"].weight


failing_cases = [
    {  # Check that it fails when the functions are not shuffled
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=[f"sub.func{i}" for i in [3, 2, 1]],
            expected_perms=set(permutations([f"sub.func{i}" for i in [3, 2, 1]])),
        ),
        "file_text": "def func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass\n\ndef main():\n    func1()\n    func2()\n    func3()\n",
    },
    {  # Check that it fails when only two functions are shuffled
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=[f"sub.func{i}" for i in [3, 2, 1]],
            expected_perms=set(permutations([f"sub.func{i}" for i in [3, 2, 1]])),
        ),
        "file_text": "import random\ndef func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass\n\ndef main():\n    funcs = [func1, func2]\n    random.shuffle(funcs)\n    for func in funcs:\n        func()\n    func3()\n",
    },
    {  # Check that it fails when the functions are not shuffled
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=[f"sub.func{i}" for i in [3, 2, 1]],
            expected_perms=set(permutations([f"sub.func{i}" for i in [3, 2, 1]])),
        ),
        "file_text": "import random\ndef func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass\n\ndef main():\n    funcs = [func1, func2, func3]\n    for func in funcs:\n        func()\n",
    },
    {  # Check that it fails when some functions are not called at all
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=[f"sub.func{i}" for i in [3, 2, 1]],
            expected_perms=set(permutations([f"sub.func{i}" for i in [3, 2, 1]])),
        ),
        "file_text": "import random\ndef func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass\n\ndef main():\n    funcs = [func1, func2]\n    random.shuffle(funcs)\n    for func in funcs:\n        func()\n",
    },
    {  # Check that it fails when some functions do not exist
        "options": Options(
            sub_module="sub",
            weight=2,
            random_func_calls=[f"sub.func{i}" for i in [3, 2, 1]],
            expected_perms=set(permutations([f"sub.func{i}" for i in [3, 2, 1]])),
        ),
        "file_text": "import random\ndef func1():\n    pass\n\ndef func2():\n    pass\n\ndef main():\n    funcs = [func1, func2]\n    random.shuffle(funcs)\n    for func in funcs:\n        func()\n",
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_failing_random_function_calls(fix_syspath, case):
    """Test that the function calls are random test fails."""
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["file_text"])
    # Create the test method
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_random_function_calls_0")
    test_method = built_instance.test_random_function_calls_0
    # Run the test method
    with pytest.raises(AssertionError) as exc_info:
        test_method()
    # Make sure the score is correct
    assert test_method.__score__ == 0
    # Make sure the error message is correct
    assert (
        "It does not appear that your functions are being called randomly.\n  Please ensure that you are calling the functions in a random order."
        in str(exc_info.value)
    )


def test_random_function_calls_init(fix_syspath, capsys):
    """Make sure an init function is called"""
    # Setup
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text("def func1():\n    pass\n\ndef main():\n    func1()\n")
    # Create the test method
    options = Options(
        sub_module="sub",
        weight=2,
        random_func_calls=["sub.func1"],
        expected_perms={("sub.func1",)},
        init=lambda: print("init"),
    )
    built_class = build(options)
    built_instance = built_class(methodName="test_random_function_calls_0")
    test_method = built_instance.test_random_function_calls_0
    # Run the test method
    assert capsys.readouterr().out == ""
    test_method()
    # Make sure the init function was called
    assert capsys.readouterr().out == "init\n"
