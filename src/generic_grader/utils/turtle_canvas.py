import turtle
from io import BytesIO
from os.path import isfile

from attrs import evolve
from PIL import Image, ImageChops

from generic_grader.utils.user import RefUser, SubUser


def save_ref_canvas(setup_func, draw_func, args, pen_width, filename, invert):
    # Setup the turtle and canvas.
    setup_func()

    # Skip animation
    turtle.tracer(0)

    turtle.width(pen_width)  # Override reference turtle width.

    # Draw the spiral.
    draw_func(*args)

    # Save the canvas and reset.
    turtle.hideturtle()
    turtle.update()
    save_canvas(turtle.getcanvas(), filename, invert)
    turtle.reset()


def save_sub_canvas(self, options):
    o = options

    if o.entries:
        sol_image_fn = f"sol_{o.entries}.png"
        sol_image_fn_inv = f"sol_{o.entries}_inv.png"
    else:
        sol_image_fn = "sol.png"
        sol_image_fn_inv = "sol_inv.png"

    # Skip if solution file already exists.
    if isfile(sol_image_fn) and isfile(sol_image_fn_inv):
        return

    # Create the reference and student user.
    ref_options = evolve(o, obj_name="start", entries=())
    self.ref_start_user = RefUser(self, ref_options)
    self.student_main_user = SubUser(self, o)

    # Initialize the turtle window using the reference modules start().
    self.ref_start_user.call_obj()

    # Skip animation
    turtle.tracer(0)

    # Call the student's function.
    self.student_main_user.call_obj()

    # Generate regular and inverted images of the submitted turtle drawing and
    # reset.
    turtle.hideturtle()
    turtle.update()  # Update canvas
    save_canvas(turtle.getcanvas(), sol_image_fn, invert=False)
    save_canvas(turtle.getcanvas(), sol_image_fn_inv, invert=True)
    turtle.reset()


def save_canvas(canvas=None, filename=None, invert=True, bw=True):
    """Save a screenshot of the canvas as filename."""
    if not canvas:
        canvas = turtle.getcanvas()

    if not filename:
        # Commenting this out to maintain the original call structure.
        # filename = Path(inspect.stack()[1].filename).with_suffix(".png")
        raise ValueError(
            "Filename must be provided in order to use this function."
        )  # Non student facing error message.
    # There has to be a better way to capture the canvas window.

    # # Things I've Tried:

    # PIL.ImageGrab.grab()
    # This eliminates the ghostscript dependency and should resolve the
    # bit rounding issues around the edges if I can find and specify the
    # window address.  Using the bound box was unreliable, capturing the
    # background unless the animation was slowed down.

    # # Things To Try

    # ImageMagick
    # import -display :1 -window ??? solution.png
    # Like ImageGrab, this would avoid the ghostscript dependency, but
    # it adds ImageMagick which is even bigger.  Still, it should
    # resolve the bit rounding (2 bit offset).

    # xwud
    # see man xvfb for an example.

    # # Current Workaround

    # Set the window scaling to 72 dpi and save the window as an eps.
    # Then import a rasterized version in Pillow and crop off some rows
    # and columns to align the image with the test images.

    # The canvas should be scaled to use 72 dpi so PILLOW will raster
    # the eps to be the exact same size as maze.png.  Unfortunately, for
    # some image sizes (630x630, and 658x658), changing the scaling from
    # the default resulted in a 1 pixel short width.  Using a size of
    # (564x564) seems to have resolved the problem.  Perhaps because it
    # is divisible by 4.
    #
    # Print the default scale factor: 1.33333333 (96 DPI)
    # print(f"scaling {canvas._root().tk.call('tk', 'scaling')}")

    # Change the scale factor to 1 (72 DPI)
    canvas.master.tk.call("tk", "scaling", 1)

    solution_eps_bytes = canvas.postscript().encode("ascii")
    with Image.open(BytesIO(solution_eps_bytes)) as solution:
        if not bw:
            # Save in color.
            if invert:
                solution = ImageChops.invert(solution)
            solution.save(filename)
            return

        # Convert from RGB to grey scale
        solution = solution.convert("L")

        # Convert from grey scale to inverted black and white
        solution = solution.point(lambda x: 0 if x == 255 else 255, "1")

        # Remove inversion if requested.
        if not invert:
            solution = ImageChops.invert(solution)

        # Remove first 2 rows and cols to correct for pixel shift.
        solution = solution.crop((2, 2, *solution.size))

        solution.save(filename)


def save_color_canvas(*args, invert=False, **kwargs):
    """Save a turtle canvas with sensible default arguments.

    This simply forwards the call to `save_canvas` with `invert` defaulting to
    false.  The interface for this function is a bit odd because I'd rather not
    change `save_canvas` right now.
    """
    save_canvas(*args, invert=invert, bw=False, **kwargs)
