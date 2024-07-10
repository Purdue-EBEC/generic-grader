"""Provide a mock user for code under test."""

import re
import resource
import signal
import sys
import textwrap
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from freezegun import freeze_time

from generic_grader.utils.docs import make_call_str, ordinalize
from generic_grader.utils.exceptions import (
    EndOfInputError,
    ExitError,
    LogLimitExceededError,
    QuitError,
    UserInitializationError,
    UserTimeoutError,
    handle_error,
)
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import Options


# Change to Lamda functions
def raise_exit_error(*args, **kwargs):
    """Raise a custom ExitError."""
    raise ExitError()


def raise_quit_error(*args, **kwargs):
    """Raise a custom QuitError."""
    raise QuitError()


@contextmanager
def time_limit(seconds):
    """A context manager to limit the execution time of an enclosed block.
    Adapted from https://stackoverflow.com/a/601168
    """

    def handler(signum, frame):
        raise UserTimeoutError(
            f"The time limit for this test is {seconds}"
            + ((seconds == 1 and " second.") or " seconds.")
        )

    signal.signal(signal.SIGALRM, handler)

    signal.alarm(seconds)  # Set an alarm to interrupt after seconds seconds.

    try:
        yield
    finally:
        # Cancel the alarm.
        signal.alarm(0)


@contextmanager
def memory_limit(max_gibibytes):
    """A context manager to limit memory usage while running submitted code.
    For soft limits above 20 MiB, the error was found experimentally to be
    raised when the total memory usage was about 10 MiB below the soft limit.
    For all soft limits less than 20 MiB, the error was raised when the total
    memory usage was about 9.2 MiB.
    """
    GiB = 2**30
    max_bytes = int(max_gibibytes * GiB)

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, hard))
    try:
        yield
    except MemoryError:
        # Restore the previous limits
        resource.setrlimit(resource.RLIMIT_AS, (soft, hard))
        message = (
            "Your program used more than the maximum allowed memory"
            f" of {max_gibibytes} GiB."
        )
        raise MemoryError(message).with_traceback(sys.exc_info()[2])
    else:
        # Restore the previous limits
        resource.setrlimit(resource.RLIMIT_AS, (soft, hard))


class __User__:
    """Manages interactions with parts of the submitted code."""

    wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

    class LogIO(StringIO):
        """A string io object with a character limit."""

        def __init__(self, log_limit=0):
            """Initialize with an unlimited default limit (0 characters)."""
            super().__init__()
            self.log_limit = log_limit

        def __len__(self):
            """Return the number of characters in the log."""
            return len(self.getvalue())

        def write(self, s):
            """Wrap inherited `write()` with a length limit check."""
            super().write(s)

            # Check if limit is exceeded after write so the offending string
            # will be in the log for debugging.
            if self.log_limit and len(self) > self.log_limit:
                raise LogLimitExceededError()

    def __init__(self, test, options: Options):
        """Initialize a user."""

        if not hasattr(self, "module"):  # This error is not student facing.
            raise UserInitializationError()
        self.test = test
        self.obj_name = options.obj_name
        self.entries = iter("")
        self.log = self.LogIO()

        # Make a list of stream positions starting from the beginning and
        # adding one at each user entry.
        self.interactions = [self.log.tell()]

        # Import the test modules obj_name object.
        self.obj = Importer.import_obj(test, self.module, self.obj_name)
        self.returned_values = None

        self.patches = [
            {"args": ["sys.stdout", self.log]},
            {"args": ["builtins.input", self.responder]},
            {
                "args": [
                    "builtins.exit",
                    raise_exit_error,
                ],
            },
            {
                "args": [
                    "builtins.quit",
                    raise_quit_error,
                ],
            },
        ]
        if options.patches:
            self.patches.extend(options.patches)

    def format_log(self, options: Options):
        """Return a formatted string of the IO log."""
        lines = self.read_log_lines(options)
        if lines:
            string = (
                "\n\nline |Input/Output Log:\n"
                + f'{70*"-"}\n'
                + "".join([f"{n+1:4d} |{line}" for n, line in enumerate(lines)])
            )
        else:
            string = ""
        return string

    def get_value(self, options: Options):
        """Return the value_n th float in line `line_n`, indexed from the
        prompt for user interaction `interaction`.
        """
        line_n = options.line_n
        value_n = options.value_n
        values = self.get_values(options)

        try:
            msg = False
            value = values[value_n - 1]
        except IndexError:
            self.test.failureException = IndexError
            value_nth = ordinalize(value_n)
            line_nth = ordinalize(line_n)
            msg = (
                "\n"
                + self.wrapper.fill(
                    f"Looking for the {value_nth} value "
                    + f"in the {line_nth} output line, "
                    + f"but only found {len(values)} value(s) "
                    + f"in line {line_n}."
                )
                + self.format_log(options)
            )

        if msg:
            self.test.fail(msg)

        return value

    def get_values(self, options: Options):
        """Return all the values matching a number like pattern in line
        `line_n`, indexed from the prompt for user interaction `interaction`.
        """
        pattern = r"""(?x:                 # Start a verbose pattern
                      -?                   # 0 or 1 leading minus signs
                      [0-9]{1,3}           # 1 to 3 digits
                      (?:                  # Start a non-capturing group
                        (?:                #   Start a non-capturing group
                          ,[0-9]{3}        #     literal comma 3 digits
                        )+                 #     1 or more times
                        |                  #   OR
                        (?:[0-9]*)         #   Any number of digits
                      )                    #
                      (?:                  # Start a non-capturing group
                        \.                 #   A literal period
                        [0-9]*             #   0 or more digits
                      )?                   # 0 or 1 times
                      (?:                  # Start a non-capturing group
                        e[+-]              #   literal e followed by + or -
                        [0-9]+             #   1 or more digits
                      )?                   # 0 or 1 times
                  )"""
        line_string = self.read_log_line(options)
        match_strings = re.findall(pattern, line_string)
        value_strings = [match.replace(",", "") for match in match_strings]

        try:
            msg = False
            values = [float(value_str) for value_str in value_strings]
        except (
            ValueError
        ) as e:  # Just in case the pattern matching fails. # pragma: no cover
            self.test.failureException = ValueError  # pragma: no cover
            msg = (
                "Test failed due to an error. "
                + f'The error was "{e.__class__.__name__}: {e}". '
                + "This is a bug in the autograder. "
                + "Please notify your instructor."
            )  # pragma: no cover
        if msg:
            self.test.fail(msg)  # pragma: no cover

        return values

    def read_log(self, options: Options):
        """Return a string of up to `n_lines` lines of IO starting from the
        prompt for user interaction `interaction`.
        """
        return "".join(self.read_log_lines(options))

    def read_log_line(self, options: Options):
        """Return line number `line_n` of IO as a string, indexed from the
        prompt for user interaction `interaction`.
        """
        line_n = options.line_n
        lines = self.read_log_lines(options)
        try:
            msg = False
            line_string = lines[line_n - 1]
        except IndexError:
            self.test.failureException = IndexError
            msg = (
                "\n"
                + self.wrapper.fill(
                    f"Looking for line {line_n}, "
                    + f"but output only has {len(lines)} lines."
                )
                + self.format_log(options)
            )
        if msg:
            self.test.fail(msg)

        return line_string

    def read_log_lines(self, options: Options):
        """Return a list of up to `n_lines` lines of IO starting from the
        prompt for user interaction `interaction`.
        """
        interaction = options.interaction
        n_lines = options.n_lines
        start = options.start
        self.log.seek(self.interactions[interaction])
        start = start and start - 1 or 0
        stop = n_lines and start + n_lines or n_lines
        return self.log.readlines()[start:stop]

    def responder(self, string=""):
        """Override for builtin input to provide simulated user responses."""

        # Save the IO stream location
        self.interactions.append(self.log.tell())

        # Log prompt
        self.log.write(string)

        # Get the user's next entry
        try:
            entry = str(next(self.entries))
        except StopIteration as e:
            # Chain StopIteration to custom EndOfInputError which can be
            # handled later.
            raise EndOfInputError from e

        # Log entry
        self.log.write(entry + "\n")

        return entry

    def call_obj(self, options: Options):
        """Have a simulated user call the object."""

        if options.entries:
            self.entries = iter(options.entries)

        if options.log_limit:
            self.log.log_limit = options.log_limit

        msg = False
        call_str = make_call_str(self.obj_name, options.args, options.kwargs)
        error_msg = "\n" + self.wrapper.fill(
            f"Your `{self.obj_name}` malfunctioned"
            + f" when called as `{call_str}`"
            + ((self.entries) and f" with entries {self.entries}." or ".")
        )
        try:
            with ExitStack() as stack:
                # Limit execution time to 1 second.
                stack.enter_context(time_limit(options.time_limit))

                # Limit memory to 1.4 GB.
                stack.enter_context(memory_limit(options.memory_limit_GB))

                if options.fixed_time:
                    # Freeze time
                    stack.enter_context(freeze_time(options.fixed_time))

                # Apply patches, this must be done last because any patches added also affect our code
                for p in self.patches:
                    stack.enter_context(
                        patch(
                            *p.get("args", ()),  # permit missing args
                            **p.get("kwargs", {}),  # permit missing kwargs
                        )
                    )

                # Call the attached object with copies of r args and kwargs.
                self.returned_values = self.obj(
                    *deepcopy(options.args), **deepcopy(options.kwargs)
                )
        except Exception as e:
            # TODO This function is going to be refactored
            self.test.failureException = type(e)
            raise e
            msg = handle_error(e, error_msg)
        else:
            try:  # Check for left over entries.
                next(self.entries)
            except StopIteration:
                pass  # The expected result.
            else:
                msg = (
                    error_msg
                    + "\n\nHint:\n"
                    + self.wrapper.fill(
                        "Your program ended before the user finished entering input."
                    )
                )

        if msg:
            # Append the IO log to the error message if it's not empty.
            log = self.log.getvalue()
            if log:
                msg += self.format_log(Options(interaction=0))

            self.test.fail(msg)

        if options.debug:
            print(self.log.getvalue())

        return self.returned_values


class RefUser(__User__):
    def __init__(self, test, options: Options):
        self.module = options.ref_module
        super().__init__(test, options)


class SubUser(__User__):
    def __init__(self, test, options: Options):
        self.module = options.sub_module
        super().__init__(test, options)
