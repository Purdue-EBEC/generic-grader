import os
import shutil
import unittest
from pathlib import Path

import pytest

from generic_grader.image.ocr_words_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(expected_words="test words"))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_build_class_type(built_class):
    """Test that the file_closed build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "OCRWordsMatchReference"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_ocr_words_match_reference_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_ocr_words_match_reference_0.__doc__
    assert 'Check the drawing for the words: "test words".' == docstring


passing_cases = [
    {
        "expected_words": "bed\nbed",
        "file_name": "bed_bed.png",
    },
    {
        "expected_words": "bed",
        "file_name": "bed.png",
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing(case, tmp_path):
    cwd = os.getcwd()
    os.chdir(tmp_path)

    def init(self, options):
        shutil.copy(
            Path(cwd) / "tests" / "image" / case["file_name"],
            tmp_path / "sol.png",
        )

    try:
        o = Options(expected_words=case["expected_words"], init=init)
        built_class = build(o)
        instance = built_class(methodName="test_ocr_words_match_reference_0")
        test_method = instance.test_ocr_words_match_reference_0
        test_method()
    finally:
        os.chdir(cwd)


def test_failing(tmp_path):
    cwd = os.getcwd()
    os.chdir(tmp_path)

    def init(self, options):
        shutil.copy(
            Path(cwd) / "tests" / "image" / "bed.png",
            tmp_path / "sol.png",
        )

    try:
        o = Options(expected_words="not the bed", init=init)
        built_class = build(o)
        instance = built_class(methodName="test_ocr_words_match_reference_0")
        test_method = instance.test_ocr_words_match_reference_0
        with pytest.raises(AssertionError) as exc_info:
            test_method()
        expected = "Hint:\n  The words found in your solution are not sufficiently similar to the\n  expected words."
        assert expected in str(exc_info.value)
    finally:
        os.chdir(cwd)
