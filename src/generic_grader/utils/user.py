"""Provide a mock user for code under test."""

import re
from copy import deepcopy
from io import StringIO

from attrs import evolve

from generic_grader.utils.docs import get_wrapper, make_call_str, ordinalize
from generic_grader.utils.exceptions import (
    EndOfInputError,
    ExtraEntriesError,
    LogLimitExceededError,
    UserInitializationError,
    handle_error,
)
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import Options
from generic_grader.utils.patches import custom_stack


class __User__:
    """Manages interactions with parts of the submitted code."""

    wrapper = get_wrapper()

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
        self.options = options
        self.entries = iter("")
        self.log = self.LogIO()

        # Make a list of stream positions starting from the beginning and
        # adding one at each user entry.
        self.interactions = [self.log.tell()]

        # Import the test modules obj_name object.
        self.obj = Importer.import_obj(test, self.module, self.options)
        self.returned_values = None

        self.patches = [
            {"args": ["sys.stdout", self.log]},
            {"args": ["builtins.input", self.responder]},
        ]
        if options.patches:
            self.patches.extend(options.patches)

    def format_log(self):
        """Return a formatted string of the IO log."""
        old_options = self.options
        self.options = evolve(old_options, n_lines=None, start=1)
        lines = self.read_log_lines()
        if lines:
            string = (
                "\n\nline |Input/Output Log:\n"
                + f'{70*"-"}\n'
                + "".join([f"{n+1:4d} |{line}" for n, line in enumerate(lines)])
            )
        else:
            string = ""
        self.options = old_options
        return string

    def get_value(self):
        """Return the value_n th float in line `line_n`, indexed from the
        prompt for user interaction `interaction`.
        """
        value_n = self.options.value_n
        line_n = self.options.line_n
        values = self.get_values()

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
                + self.format_log()
            )

        if msg:
            self.test.fail(msg)

        return value

    def get_values(self, line_string: str | None = None):
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
        if line_string is None:
            line_string = self.read_log_line()
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

    def read_log(self):
        """Return a string of up to `n_lines` lines of IO starting from the
        prompt for user interaction `interaction`.
        """
        return "".join(self.read_log_lines())

    def read_log_line(self):
        """Return line number `line_n` of IO as a string, indexed from the
        prompt for user interaction `interaction`.
        """
        line_n = self.options.line_n
        lines = self.read_log_lines()
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
                + self.format_log()
            )
        if msg:
            self.test.fail(msg)

        return line_string

    def read_log_lines(self):
        """Return a list of up to `n_lines` lines of IO starting from the
        prompt for user interaction `interaction`.
        """
        interaction = self.options.interaction
        self.log.seek(self.interactions[interaction])
        start = self.options.start
        start = start - 1 if start else 0
        n_lines = self.options.n_lines
        stop = start + n_lines if n_lines else n_lines
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

    def call_obj(self):
        """Have a simulated user call the object."""

        o = self.options

        if o.entries:
            self.entries = iter(o.entries)

        if o.log_limit:
            self.log.log_limit = o.log_limit

        msg = False
        call_str = make_call_str(o.obj_name, o.args, o.kwargs)
        error_msg = "\n" + self.wrapper.fill(
            f"Your `{o.obj_name}` malfunctioned"
            + f" when called as `{call_str}`"
            + ((o.entries) and f" with entries {o.entries}." or ".")
        )
        try:
            stack_o = evolve(o, patches=self.patches)
            with custom_stack(stack_o):
                # Call the attached object with copies of r args and kwargs.
                self.returned_values = self.obj(*deepcopy(o.args), **deepcopy(o.kwargs))
        except Exception as e:
            # TODO This function is going to be refactored
            self.test.failureException = type(e)
            msg = handle_error(e, error_msg)
        else:
            try:  # Check for left over entries.
                next(self.entries)
            except StopIteration:
                pass  # The expected result.
            else:
                self.test.failureException = ExtraEntriesError
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
                # TODO add testcase to determine if this is intended
                msg += self.format_log()

            self.test.fail(msg)

        if o.debug:
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
