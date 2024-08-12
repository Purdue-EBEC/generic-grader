import unittest

import pytest
from PIL import Image, ImageChops

from generic_grader.image.pixel_overlap import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(
        Options(region_inner="path", region_outer="walls", mode="exactly", threshold=0)
    )


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_build_class_type(built_class):
    """Test that the file_closed build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestPixelOverlap"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_pixel_overlap_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_pixel_overlap_0.__doc__
    assert (
        "Check that the path from your `main` function when called as "
        "`main()` has exactly 0 pixels in the walls." == docstring
    )


def test_entries_doc_func():
    o = Options(
        region_inner="path",
        region_outer="walls",
        mode="exactly",
        threshold=0,
        entries=(1, 2, 3),
    )
    built_class = build(o)
    instance = built_class()
    docstring = instance.test_pixel_overlap_0.__doc__
    assert (
        "Check that the path from your `main` function when called as "
        "`main()` with entries=(1, 2, 3) has exactly 0 pixels in the walls."
        == docstring
    )


pixel_cases = [
    {
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="exactly",
            threshold=0,
        ),
        "ref_image": None,
        "sub_image": None,
        "error": None,
    },
    {
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="exactly",
            threshold=100,
        ),
        "ref_image": 10,
        "sub_image": 10,
        "error": None,
    },
    {
        # Check that the sub_image has less than 100 pixels in the ref_image.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="less than",
            threshold=100,
        ),
        "ref_image": 100,
        "sub_image": 9,
        "error": None,
    },
    {  # Check that even when the ref_image has no pixels the mode passes.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="less than",
            threshold=100,
        ),
        "ref_image": 0,
        "sub_image": 10,
        "error": None,
    },
    {  # Check that the sub_image has more than 100 pixels in the ref_image.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="more than",
            threshold=100,
        ),
        "ref_image": 100,
        "sub_image": 101,
        "error": None,
    },
    {  # Check that even when the ref_image more pixels than
        # the sub_image the mode passes.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="more than",
            threshold=100,
        ),
        "ref_image": 100,
        "sub_image": 99,
        "error": None,
    },
    {  # Check that the sub_image has approximately 100 pixels in the ref_image.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="approximately",
            threshold=100,
            delta=19,
        ),
        "ref_image": 10,
        "sub_image": 9,
        "error": None,
    },
    {  # Check that when the two images are the same the approximately mode passes.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="approximately",
            threshold=100,
            delta=0,
        ),
        "ref_image": 10,
        "sub_image": 10,
        "error": None,
    },
    {  # Check that even when sub_image has more pixels than ref_image the mode passes.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="approximately",
            threshold=100,
            delta=0,
        ),
        "ref_image": 10,
        "sub_image": 100,
        "error": None,
    },
    {  # Check that when the two images are different the exactly mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="exactly",
            threshold=100,
        ),
        "ref_image": 10,
        "sub_image": 9,
        "error": AssertionError,
    },
    {  # Check that when the sub_image has more pixels than expected the mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="less than",
            threshold=100,
        ),
        "ref_image": 100,
        "sub_image": 200,
        "error": AssertionError,
    },
    {  # Check that when the two images are on the threshold the less than mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="less than",
            threshold=100,
        ),
        "ref_image": 10,
        "sub_image": 10,
        "error": AssertionError,
    },
    {  # Check that when the sub_image has less pixels than expected the mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="more than",
            threshold=100,
        ),
        "ref_image": 10,
        "sub_image": 9,
        "error": AssertionError,
    },
    {  # Check that when the two images are on the threshold the more than mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="more than",
            threshold=100,
        ),
        "ref_image": 10,
        "sub_image": 10,
        "error": AssertionError,
    },
    {  # Check that when the sub_image has no pixels the mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="more than",
            threshold=100,
        ),
        "ref_image": 100,
        "sub_image": 0,
        "error": AssertionError,
    },
    {  # Check that when the sub_image is outside the delta the mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="approximately",
            threshold=100,
            delta=10,
        ),
        "ref_image": 100,
        "sub_image": 9,
        "error": AssertionError,
    },
    {  # Check that when the sub_image has no pixels the mode fails.
        "options": Options(
            ref_image="ref_image.png",
            sub_image="sub_image.png",
            mode="approximately",
            threshold=100,
            delta=10,
        ),
        "ref_image": 100,
        "sub_image": 0,
        "error": AssertionError,
    },
]


@pytest.mark.parametrize("case", pixel_cases)
def test_pixel_overlap(case, fix_syspath):
    """Test that the test_pixel_overlap method works as expected."""

    o = case["options"]
    ref_size = case["ref_image"]
    sub_size = case["sub_image"]
    # Create the blank images.
    width, height = 1000, 1000
    ref_image = Image.new("RGB", (width, height), color="white")
    sub_image = Image.new("RGB", (width, height), color="white")
    # Paste black pixels into the images.
    if ref_size:
        ref_image.paste(0, box=(0, 0, ref_size, ref_size))
    if sub_size:
        sub_image.paste(0, box=(0, 0, sub_size, sub_size))
    # Convert the images to the correct format.
    ref_image = ImageChops.invert(ref_image.convert("1"))
    sub_image = ImageChops.invert(sub_image.convert("1"))
    # Save the images.
    ref_image.save(o.ref_image)
    sub_image.save(o.sub_image)
    # Create the built class and instance.
    built_class = build(o)
    instance = built_class(methodName="test_pixel_overlap_0")
    if case["error"]:
        with pytest.raises(case["error"]):
            instance.test_pixel_overlap_0()
    else:
        instance.test_pixel_overlap_0()


def test_init(fix_syspath, capsys):
    """Test that the init function works as expected."""

    # Create a fake init function.
    def init(self, options):
        print("Hello, World!")

    o = Options(
        ref_image="ref_image.png",
        sub_image="sub_image.png",
        init=init,
    )
    # Create the blank images.
    width, height = 1000, 1000
    ref_image = Image.new("RGB", (width, height), color="white")
    sub_image = Image.new("RGB", (width, height), color="white")
    ref_image = ImageChops.invert(ref_image.convert("1"))
    sub_image = ImageChops.invert(sub_image.convert("1"))
    ref_image.save(o.ref_image)
    sub_image.save(o.sub_image)
    # Create the built class and instance
    built_class = build(o)
    instance = built_class(methodName="test_pixel_overlap_0")
    instance.test_pixel_overlap_0()
    # Check that the init function was called.
    captured = capsys.readouterr()
    assert "Hello, World!" in captured.out
