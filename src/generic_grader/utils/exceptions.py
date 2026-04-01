import traceback
from os import path

from generic_grader.utils.docs import get_wrapper

inf_loop_hint = "Make sure your program isn't stuck in an infinite loop."
return_hint = "Try using a `return` statement instead."

wrapper = get_wrapper()


def indent(string, pad="  "):
    return "\n".join([pad + line for line in string.splitlines()])


def safe_exception_type(exc_type):
    """Wrap exception types whose __str__ uses repr() on the message.

    KeyError.__str__() returns repr(args[0]) instead of str(args[0]),
    which escapes newlines to literal '\\n' characters. This makes
    multi-line error messages unreadable when displayed to students.

    Returns a subclass with standard __str__ behavior that preserves
    the original exception type name for display purposes.
    """
    if exc_type is KeyError:

        class SafeKeyError(KeyError):
            def __str__(self):
                return self.args[0] if self.args else ""

        SafeKeyError.__name__ = "KeyError"
        SafeKeyError.__qualname__ = "KeyError"
        return SafeKeyError
    return exc_type


def format_error_msg(error_msg, hint=None):
    hint = f"\n\nHint:\n{wrapper.fill(hint)}" if hint else ""
    return f"{wrapper.fill(error_msg)}{hint}"


def handle_error(e, error_msg):
    stack_summary = traceback.extract_tb(e.__traceback__)
    short_stack_summary = []
    for frame_summary in stack_summary:
        dirname, filename = path.split(frame_summary.filename)

        # Skip frames from the autograding system. This includes:
        # - /tests: test runner frames
        # - /usr: system Python library frames
        # - <string>: dynamically compiled code
        # - generic_grader: the grader package itself (e.g., when
        #   installed via uv into a virtualenv)
        if (
            "/tests" in dirname
            or "/usr" in dirname
            or "generic_grader" in dirname
            or filename == "<string>"
        ):
            continue

        # Remove the path information from the filename in each frame
        # summary.  This makes the error message clearer while also
        # hiding the autograder's directory structure.
        frame_summary.filename = filename

        short_stack_summary.append(frame_summary)

    # Format the traceback with special handling for syntax errors.
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


class _GraderError(Exception):
    """Base class for grader exceptions.

    Handles the dual calling convention: either constructed normally via
    _build_msg(), or re-raised by test.fail() with a preformatted message
    (detected by the presence of newlines in the first argument).
    """

    def __init__(self, *args):
        if args and isinstance(args[0], str) and "\n" in args[0]:
            self.msg = args[0]
        else:
            self.msg = self._build_msg(*args)
        super().__init__(self.msg)

    def __str__(self):
        return self.msg

    def _build_msg(self, *args):
        raise NotImplementedError  # pragma: no cover


class ExitError(_GraderError):
    """Custom Exception to raise when submitted code calls `exit()`."""

    def _build_msg(self, hint=None):
        hint = f"{hint}  {return_hint}" if hint else return_hint
        return format_error_msg(
            "Calling the `exit()` function is not allowed in this course.", hint
        )


class QuitError(_GraderError):
    """Custom Exception to raise when submitted code calls `quit()`."""

    def _build_msg(self, hint=None):
        hint = f"{hint}  {return_hint}" if hint else return_hint
        return format_error_msg(
            "Calling the `quit()` function is not allowed in this course.", hint
        )


class LogLimitExceededError(_GraderError):
    """Custom Exception to raise when the log length exceeds some limit."""

    def _build_msg(self, hint=None):
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        return format_error_msg(
            "Your program produced much more output than was expected.", hint
        )


class UserTimeoutError(_GraderError):
    """Custom Exception to raise when submitted code doesn't return within one
    second.
    """

    def _build_msg(self, hint=None):
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        return format_error_msg("Your program ran for longer than expected.", hint)


class EndOfInputError(_GraderError):
    """Custom Exception to raise when submitted code requests too much input."""

    def _build_msg(self, hint=None):
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        return format_error_msg(
            "Your program requested user input more times than expected.", hint
        )


class ExtraEntriesError(_GraderError):
    """Custom Exception to raise when submitted code requests not enough input."""

    def _build_msg(self, hint=None):
        return format_error_msg(
            "Your program requested user input less times than expected.", hint
        )


class ExcessFunctionCallError(_GraderError):
    """Custom Exception to raise when submitted code calls a function more
    times than expected.
    """

    def _build_msg(self, func_name=None, hint=None):
        error_msg = (
            f"Your program called the `{func_name}` function more times than expected."
        )
        hint = f"{hint}  {inf_loop_hint}" if hint else inf_loop_hint
        return format_error_msg(error_msg, hint)


class TurtleWriteError(_GraderError):
    """Some custom exception."""

    def _build_msg(self, error_msg=""):
        hint = (
            "The turtle module's `write` function"
            " is not allowed in this exercise."
            "  Try using turtle movement commands to draw each letter instead."
        )
        return format_error_msg(error_msg, hint)


class TurtleDoneError(_GraderError):
    """Some custom exception."""

    def _build_msg(self, error_msg=""):
        hint = (
            "The turtle module's `done` function"
            " should not be called from within any of your functions."
            "  The only call to `done()` in your program should be the one"
            " included in the exercise template."
        )
        return format_error_msg(error_msg, hint)


class UserInitializationError(_GraderError):
    """Custom Exception to raise when a regular User Class is created"""

    def _build_msg(self):
        return format_error_msg(
            "The User class should not be directly instantiated. Use `RefUser` or SubUser` instead.",
            None,
        )


class RefFileNotFoundError(_GraderError):
    """Exception for failed reference solution file creation."""

    def _build_msg(self, filename):
        return format_error_msg(
            f"The reference solution failed to create the required file `{filename}`.",
            None,
        )
