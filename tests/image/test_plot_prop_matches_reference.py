import unittest

import pytest

from generic_grader.image.plot_prop_matches_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(prop="fake_prop"))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_plot_prop_matches_reference_build_class(built_class):
    """Test that the plot_prop build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_plot_prop_matches_reference_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestPlotPropMatchesReference"


def test_plot_prop_matches_reference_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_plot_prop_matches_reference_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_plot_prop_matches_reference_0")


def test_plot_prop_matches_reference_doc_func_test_string(built_instance):
    """Test that the built_class has the correct docstring."""
    assert built_instance.test_plot_prop_matches_reference_0.__doc__ == (
        "Check that the fake_prop in the plot generated"
        " from your `main` function when called as `main()`"
        " matches the reference."
    )


plot_one_text = (
    "import matplotlib.pyplot as plt\n"
    "def main():\n"
    "    fig, ax = plt.subplots()\n"
    "    ax.plot([1, 2, 3, 4], [1, 4, 9, 16])\n"
    "    ax.set_title('Simple plot')\n"
    "    ax.set_xlabel('x-axis')\n"
    "    ax.set_ylabel('y-axis')\n"
)

plot_two_text = (
    "import matplotlib.pyplot as plt\n"
    "def main():\n"
    "    fig, ax = plt.subplots()\n"
    "    ax.plot([1, 2, 3, 4, 5], [1, 4, 9, 16, 25])\n"
    "    ax.set_title('Simple plot 2')\n"
    "    ax.set_xlabel('fake line on bottom')\n"
    "    ax.set_ylabel('y-axis-2')\n"
)

passing_cases = [
    {  # Plot matches reference str with ratio
        "submission": plot_one_text,
        "reference": plot_two_text,
        "options": Options(
            prop="title", weight=1, ratio=0.8, ref_module="ref", sub_module="sub"
        ),
    },
    {  # Plot matches reference list
        "submission": plot_one_text,
        "reference": plot_one_text,
        "options": Options(prop="x data", weight=1, ref_module="ref", sub_module="sub"),
    },
    {  # Plot matches xy data
        "submission": plot_one_text,
        "reference": plot_one_text,
        "options": Options(
            prop="xy data", weight=1, ref_module="ref", sub_module="sub"
        ),
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_plot_prop_matches_reference_passing_cases(fix_syspath, case):
    """Test that the plot matches the reference. For all three cases."""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["reference"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["submission"])

    built_class = build(case["options"])
    built_instance = built_class(methodName="test_plot_prop_matches_reference_0")
    test_method = built_instance.test_plot_prop_matches_reference_0

    test_method()

    assert test_method.__score__ == case["options"].weight


failing_cases = [
    {  # Plot does not match reference str with ratio
        "submission": plot_one_text,
        "reference": plot_two_text,
        "options": Options(
            prop="x label", weight=1, ratio=0.8, ref_module="ref", sub_module="sub"
        ),
        "msg": (
            "Hint:\n"
            "  Your plot did not match the expected plot.  Double check the x label\n"
            "  in the plot produced by your `main` function when called as\n"
            "  `main()`.  The words found in your solution are not sufficiently\n"
            "  similar to the expected words."
        ),
    },
    {  # Plot does not match reference list
        "submission": plot_one_text,
        "reference": plot_two_text,
        "options": Options(prop="x data", weight=1, ref_module="ref", sub_module="sub"),
        "msg": "Double check the x data\n  in the plot produced by your `main` function when called as\n  `main()`.",
    },
    {  # Plot does not match xy data
        "submission": plot_one_text,
        "reference": plot_two_text,
        "options": Options(
            prop="xy data", weight=1, ref_module="ref", sub_module="sub"
        ),
        "msg": "Double check the xy data\n  in the plot produced by your `main` function when called as\n  `main()`.",
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_plot_prop_matches_reference_failing_cases(fix_syspath, case):
    """Test that the plot does not match the reference.""" ""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["reference"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["submission"])

    built_class = build(case["options"])
    built_instance = built_class(methodName="test_plot_prop_matches_reference_0")
    test_method = built_instance.test_plot_prop_matches_reference_0
    with pytest.raises(AssertionError) as exc_info:
        test_method()
    assert case["msg"] in str(exc_info.value)

    assert test_method.__score__ == 0


def test_plot_prop_matches_reference_init(fix_syspath, capsys):
    """Test that the init function is called."""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(plot_one_text)
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(plot_one_text)

    def fake_init():
        print("fake init")

    options = Options(
        prop="title", weight=1, ref_module="ref", sub_module="sub", init=fake_init
    )
    built_class = build(options)
    built_instance = built_class(methodName="test_plot_prop_matches_reference_0")
    test_method = built_instance.test_plot_prop_matches_reference_0
    test_method()
    captured = capsys.readouterr()
    assert "fake init" in captured.out
