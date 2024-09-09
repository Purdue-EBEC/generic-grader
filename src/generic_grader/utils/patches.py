from generic_grader.utils.exceptions import TurtleDoneError, TurtleWriteError
from generic_grader.utils.mocks import make_mock_function_raise_error


def make_turtle_done_patches(modules):
    """Patch extra calls to done()/mainloop() to prevent hangs when the student
    mistakenly calls one of them.  The `modules` parameter should be a list or
    tuple of the assignment's module names. E.g. `modules = ["vowels",
    "random_vowels"]`."""
    return [
        {"args": make_mock_function_raise_error(f"{module}.{func}", TurtleDoneError)}
        for func in ["done", "mainloop"]
        for module in ["turtle", *modules]
    ]


def make_turtle_write_patches(modules):
    """Make patches to block access to `turtle.write`. The `modules` parameter
    should be a list or tuple of the assignment's module names. E.g. `modules =
    ["vowels", "random_vowels"]`."""
    return [
        {"args": make_mock_function_raise_error(f"{module}.write", TurtleWriteError)}
        for module in ["turtle", *modules]
    ]
