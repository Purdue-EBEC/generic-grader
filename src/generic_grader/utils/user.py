"""Provide a mock user for code under test."""

import re
from io import StringIO

from attrs import evolve

from generic_grader.runtimes import get_runtime
from generic_grader.runtimes.octave import (
    OctaveNotInstalledError,
    OctaveRuntimeError,
    OctaveTimeoutError,
)
from generic_grader.utils.attribution import report_grader_fault
from generic_grader.utils.docs import get_wrapper, make_call_str, ordinalize
from generic_grader.utils.exceptions import (
    EndOfInputError,
    ExtraEntriesError,
    LogLimitExceededError,
    UserInitializationError,
    handle_error,
    safe_exception_type,
)
from generic_grader.utils.options import Options


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

        # Pick the language runtime.  For the historical default
        # (``language="python"``) this preserves the exact
        # ``Importer.import_obj`` + ``custom_stack`` behavior; Octave
        # (and any future language) plugs in via the same seam without
        # touching the tests below that consume ``self.log``,
        # ``self.returned_values``, etc.
        self.runtime = get_runtime(options.language)()
        self.obj = self.runtime.resolve(test, self.options, self.module)
        self.returned_values = None
        # Runtime-supplied side artifacts (e.g. captured plot properties
        # from the Octave runtime).  Populated in ``call_obj`` when a
        # ``run`` produces them; kept empty for the Python runtime,
        # which reads matplotlib global state directly.
        self.artifacts: dict = {}

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
                + f"{70 * '-'}\n"
                + "".join([f"{n + 1:4d} |{line}" for n, line in enumerate(lines)])
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
            # For the Python runtime, self.patches contains the
            # sys.stdout / builtins.input redirection that the runtime
            # applies inside custom_stack.  For non-Python runtimes
            # the runtime consumes ``self.entries`` directly (e.g.
            # Octave pipes them to the child's stdin) and writes
            # captured output straight into ``self.log`` — the
            # patches list is only meaningful in-process.
            stack_o = evolve(o, patches=self.patches)
            result = self.runtime.run(stack_o, self.obj, self.log, self.entries)
            self.returned_values = result.returned_values
            self.artifacts = result.artifacts
        except OctaveTimeoutError as e:
            # Language-independent timeout: surface a TimeoutError so
            # existing test-plumbing that keys off exception types
            # continues to work.
            self.test.failureException = TimeoutError
            msg = error_msg + "\n\nHint:\n" + self.wrapper.fill(str(e))
        except OctaveRuntimeError as e:
            # Show Octave's own error text as the hint — it already
            # points at the offending line inside the .m file.
            self.test.failureException = RuntimeError
            hint = e.stderr.strip() or str(e)
            msg = error_msg + "\n\nHint:\n" + self.wrapper.fill(hint)
        except OctaveNotInstalledError as e:
            # Grader-configuration failure, not a student mistake.
            self.test.failureException = RuntimeError
            msg = "\n" + self.wrapper.fill(str(e))
        # Broad catch is deliberate: student code can raise anything, and every
        # failure must be classified (student error vs. grader fault).
        except Exception as e:  # noqa: BLE001
            # TODO This function is going to be refactored
            if fault := report_grader_fault(e):
                # A security exception raised from library code is a grader
                # bug, not a student error.  `failureException` stays at its
                # default: this is not a student exception type.
                msg = "\n" + self.wrapper.fill(
                    f"Your `{o.obj_name}` could not be checked because the "
                    f"autograder encountered an internal error "
                    f"({fault}). This is a bug "
                    "in the autograder. Please notify your instructor."
                )
            else:
                self.test.failureException = safe_exception_type(type(e))
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
