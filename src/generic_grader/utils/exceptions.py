import traceback
from os import path

from generic_grader.utils.docs import get_wrapper

inf_loop_hint = "Make sure your program isn't stuck in an infinite loop."
return_hint = "Try using a `return` statement instead."

wrapper = get_wrapper()


def indent(string, pad="  "):
    return "\n".join([pad + line for line in string.splitlines()])


def format_error_msg(error_msg, hint=None):
    hint = f"\n\nHint:\n{wrapper.fill(hint)}" if hint else ""
    return f"{wrapper.fill(error_msg)}{hint}"


# TODO: Fix problem where some filepaths still show up in the error message
def handle_error(e, error_msg):
    stack_summary = traceback.extract_tb(e.__traceback__)
    short_stack_summary = []
    for frame_summary in stack_summary:
        dirname, filename = path.split(frame_summary.filename)

        # Skip frames from the autograding system. This is usually the
        # first frame, which contains the call to the submitted code in
        # this try block, and the last 1 or 2 frames which typically
        # contain the patched function.
        if "/tests" in dirname or "/usr" in dirname or filename == "<string>":
            continue

        # Remove the path information from the filename in each frame
        # summary.  This makes the error message clearer while also
        # hiding the autograder's directory structure.
        frame_summary.filename = filename

        short_stack_summary.append(frame_summary)

    # Format the traceback with special handling for syntax errors.
    # TODO: Fix problem where some filepaths still show up in the error message
    if isinstance(e, SyntaxError):
        # Remove the path information from the filename.
        dirname, filename = path.split(e.filename)
        e.filename = filename

    formatted_traceback = (
        (
            "Traceback (most recent call last):\n"
            + "".join(traceback.format_list(short_stack_summary))
        )
        if short_stack_summary
        else ""
    ) + "".join(traceback.format_exception_only(e))

    return indent(error_msg + "\n\n" + formatted_traceback)


class ExitError(Exception):
    """Custom Exception to raise when submitted code calls `exit()`."""

    def __init__(self, hint=None):
        error_msg = "Calling the `exit()` function is not allowed in this course."
        hint = f"{hint}  {return_hint}" if hint else return_hint
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class QuitError(Exception):
    """Custom Exception to raise when submitted code calls `quit()`."""

    def __init__(self, hint=None):
        error_msg = "Calling the `quit()` function is not allowed in this course."
        hint = f"{hint}  {return_hint}" if hint else return_hint
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class LogLimitExceededError(Exception):
    """Custom Exception to raise when the log length exceeds some limit."""

    def __init__(self, hint=None):
        error_msg = "Your program produced much more output than was expected."
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class UserTimeoutError(Exception):
    """Custom Exception to raise when submitted code doesn't return within one
    second.
    """

    def __init__(self, hint=None):
        error_msg = "Your program ran for longer than expected."
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class EndOfInputError(Exception):
    """Custom Exception to raise when submitted code requests too much input."""

    def __init__(self, hint=None):
        error_msg = "Your program requested user input more times than expected."
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class ExtraEntriesError(Exception):
    """Custom Exception to raise when submitted code requests not enough input."""

    def __init__(self, hint=None):
        error_msg = "Your program requested user input less times than expected."
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class ExcessFunctionCallError(Exception):
    """Custom Exception to raise when submitted code calls a function more
    times than expected.
    """

    def __init__(self, func_name, hint=None):
        error_msg = (
            f"Your program called the `{func_name}` function"
            " more times than expected."
        )
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class TurtleWriteError(Exception):
    """Some custom exception."""

    def __init__(self, error_msg=""):
        hint = (
            "The turtle module's `write` function"
            " is not allowed in this exercise."
            "  Try using turtle movement commands to draw each letter instead."
        )
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class TurtleDoneError(Exception):
    """Some custom exception."""

    def __init__(self, error_msg=""):
        hint = (
            "The turtle module's `done` function"
            " should not be called from within any of your functions."
            "  The only call to `done()` in your program should be the one"
            " included in the exercise template."
        )
        self.msg = format_error_msg(error_msg, hint)

    def __str__(self):
        return self.msg


class UserInitializationError(Exception):
    """Custom Exception to raise when a regular User Class is created"""

    def __init__(self):
        error_msg = "The User class should not be directly instantiated. Use `RefUser` or SubUser` instead."
        self.msg = format_error_msg(error_msg, None)

    def __str__(self):
        return self.msg


class RefFileNotFoundError(Exception):
    """Exception for failed reference solution file creation."""

    def __init__(self, filename):
        error_msg = (
            f"The reference solution failed to create the required file `{filename}`."
        )
        self.msg = format_error_msg(error_msg, None)

    def __str__(self):
        return self.msg
