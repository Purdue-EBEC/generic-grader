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
    save_canvas(canvas, "test_save_canvas.png", invert=False, bw=True)
    screen.clear()

    # Load the image and check it.
    img = Image.open("test_save_canvas.png")

    img_center = img.getpixel((img.width // 2, img.height // 2))
    assert img_center == 255


# def test_save_canvas_defaults(fix_syspath):
#     """Test the save_canvas function. This has to be done first to ensure the rest of the tests behave as expected."""


#     # Save the canvas.
#     save_canvas()
#     import os
#     print(os.listdir())
#     # Load the image and check it.
#     img = Image.open("test_save_canvas.png")

#     assert img.getpixel((0, 0)) == 255


def test_save_cavas_color(fix_syspath):
    """Test the save_canvas function. This has to be done first to ensure the rest of the tests behave as expected."""

    # Create a simple canvas.
    screen = turtle.Screen()
    screen.tracer(0)
    turtle.goto(-564 / 2, -564 / 2)
    turtle.begin_fill()
    turtle.fillcolor("blue")
    turtle.goto(564 / 2, -564 / 2)
    turtle.goto(564 / 2, 564 / 2)
    turtle.goto(-564 / 2, 564 / 2)
    turtle.goto(-564 / 2, -564 / 2)
    turtle.end_fill()
    screen.update()
    canvas = screen.getcanvas()
    canvas.update()
    turtle.reset()

    save_color_canvas(canvas, "test_save_canvas_color.png", invert=False)
    screen.clear()
    # Load the image and check it.
    img = Image.open("test_save_canvas_color.png")
    img_center = img.getpixel((img.width // 2, img.height // 2))
    assert img_center == (0, 0, 255)


def test_save_color_canvas_invert(fix_syspath):
    # Create a simple canvas.
    screen = turtle.Screen()
    screen.tracer(0)
    t = turtle.Turtle()
    t.pencolor("blue")
    t.pensize(100)
    turtle.goto(-564 / 2, -564 / 2)
    turtle.begin_fill()
    turtle.fillcolor("blue")
    turtle.goto(564 / 2, -564 / 2)
    turtle.goto(564 / 2, 564 / 2)
    turtle.goto(-564 / 2, 564 / 2)
    turtle.goto(-564 / 2, -564 / 2)
    turtle.end_fill()
    screen.update()
    canvas = screen.getcanvas()
    canvas.update()
    turtle.reset()

    save_color_canvas(canvas, "test_save_canvas_color_inv.png", invert=True)
    screen.clear()
    # Load the image and check it.
    img = Image.open("test_save_canvas_color_inv.png")
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
    file_1.write_text("")
    file_2.write_text("")
    mock_test = MockTest()
    mock_test.mock_save_sub_canvas(Options())

    assert not hasattr(mock_test, "ref_start_user")
