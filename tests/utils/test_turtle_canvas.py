"""Make sure that when running these tests a display is configured."""

import turtle
import unittest

import pytest
from PIL import Image

from generic_grader.utils.options import Options
from generic_grader.utils.turtle_canvas import (
    save_canvas,
    save_color_canvas,
    save_ref_canvas,
    save_sub_canvas,
)


@pytest.fixture(autouse=True, scope="module")
def close_turtle():
    yield
    turtle.bye()


def test_save_canvas(fix_syspath):
    """Test the save_canvas function. This has to be done first to ensure the rest of the tests behave as expected."""
    # Create a simple canvas.
    screen = turtle.Screen()
    canvas = screen.getcanvas()
    canvas.update()

    # Save the canvas.
    save_canvas(filename="test_save_canvas.png", invert=False, bw=True)
    screen.clear()

    # Load the image and check it.
    img = Image.open("test_save_canvas.png")

    img_center = img.getpixel((img.width // 2, img.height // 2))
    assert img_center == 255


def test_save_canvas_defaults(fix_syspath):
    """Test that the save_canvas function raises an exception when no filename is provided."""

    # Save the canvas.
    with pytest.raises(ValueError) as exc_info:
        save_canvas(invert=False, bw=True)

    assert (
        exc_info.value.args[0]
        == "Filename must be provided in order to use this function."
    )


def test_save_cavas_color(fix_syspath):
    """Test the save_canvas function. This has to be done first to ensure the rest of the tests behave as expected."""

    # Create a simple canvas.
    screen = turtle.Screen()
    screen.tracer(0)
    turtle.pencolor("blue")
    turtle.pensize(100)
    turtle.circle(20)
    screen.update()
    canvas = screen.getcanvas()

    save_color_canvas(
        canvas=canvas, filename="test_save_canvas_color.png", invert=False
    )
    # Load the image and check it.
    img = Image.open("test_save_canvas_color.png")
    img_center = img.getpixel((img.width // 2, img.height // 2))
    assert img_center == (0, 0, 255)


def test_save_cavas_color_invert(fix_syspath):
    """Test the save_canvas function. This has to be done first to ensure the rest of the tests behave as expected."""

    # Create a simple canvas.
    screen = turtle.Screen()
    screen.tracer(0)
    turtle.pencolor("blue")
    turtle.pensize(100)
    turtle.circle(20)
    screen.update()
    canvas = screen.getcanvas()

    save_color_canvas(canvas=canvas, filename="test_save_canvas_color.png", invert=True)
    # Load the image and check it.
    img = Image.open("test_save_canvas_color.png")
    img_center = img.getpixel((img.width // 2, img.height // 2))
    assert img_center == (255, 255, 0)


def test_save_ref_canvas(fix_syspath, capsys):
    """Test the save_ref_canvas function."""

    def setup():
        print("setup")

    def draw():
        turtle.speed(0)
        turtle.pensize(100)
        turtle.color("black")
        turtle.circle(20)

    save_ref_canvas(setup, draw, [], 100, "test_save_ref_canvas.png", invert=False)

    turtle.Turtle().screen.clear()
    # Load the image and check it.
    img = Image.open("test_save_ref_canvas.png")
    img_center = img.getpixel((img.width // 2, img.height // 2))
    assert img_center == 0

    assert capsys.readouterr().out == "setup\n"


class MockTest(unittest.TestCase):
    """Mock test class for testing the save_sub_canvas function."""

    mock_save_sub_canvas = save_sub_canvas


sub_canvas_cases = [
    {
        "img1": "sol.png",
        "img2": "sol_inv.png",
        "sub_file": "from turtle import Turtle\ndef main():\n    t = Turtle()\n    t.circle(5)",
        "entries": (),
    },
    {
        "img1": "sol_(7,).png",
        "img2": "sol_(7,)_inv.png",
        "sub_file": "from turtle import Turtle\ndef main():\n    t = Turtle()\n    t.circle(int(input()))",
        "entries": (7,),
    },
]


@pytest.mark.parametrize("case", sub_canvas_cases)
def test_save_sub_canvas(fix_syspath, case):
    ref_file = fix_syspath / "ref.py"
    sub_file = fix_syspath / "sub.py"
    ref_file.write_text(
        "from turtle import setup, width\ndef start():\n    setup(564, 564)\n    width(5)"
    )
    sub_file.write_text(case["sub_file"])

    o = Options(ref_module="ref", sub_module="sub", entries=case["entries"])

    mock_test = MockTest()
    mock_test.mock_save_sub_canvas(o)
    turtle.Turtle().screen.clear()

    img_1 = Image.open(case["img1"])
    img_2 = Image.open(case["img2"])

    img_center_1 = img_1.getpixel((img_1.width // 2, img_1.height // 2))
    img_center_2 = img_2.getpixel((img_2.width // 2, img_2.height // 2))

    assert img_center_1 == 0
    assert img_center_2 == 255


def test_shortcut_sub_canvas(fix_syspath):
    file_1 = fix_syspath / "sol.png"
    file_2 = fix_syspath / "sol_inv.png"
    file_1.write_text("Check that the file is not overwritten.")
    file_2.write_text("")
    mock_test = MockTest()
    mock_test.mock_save_sub_canvas(Options())

    assert file_1.read_text() == "Check that the file is not overwritten."
