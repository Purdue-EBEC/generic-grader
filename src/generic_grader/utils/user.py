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
    safe_exception_type,
)
from generic_grader.utils.importer import SANDBOX_OBJ_SENTINEL, Importer
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

        if o.use_sandbox:
            return self._sandbox_call_obj()

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

    # ------------------------------------------------------------------
    # Sandbox path (Layer 3, gated on Options.use_sandbox)
    # ------------------------------------------------------------------

    def _sandbox_call_obj(self):
        """Sandbox-backed equivalent of `call_obj`.

        Runs the student call in a fresh isolate worker, then replays
        the worker's events into this user's existing `LogIO` and
        `interactions` so downstream helpers (`read_log_line`,
        `format_log`, `get_value`, …) see the same data they would in
        the legacy in-process path.

        Sentinel check
        --------------
        `self.obj` should be `SANDBOX_OBJ_SENTINEL` here (set by
        `Importer._sandbox_import_obj`).  We don't strictly require it
        -- tests may stub `self.obj` directly -- but the check guards
        against accidentally mixing the two paths.
        """
        from generic_grader.sandbox.integration import (
            classify_call_outcome,
            sandbox_call_obj,
        )

        o = self.options
        # `self.module` is set on subclasses (RefUser / SubUser).
        if self.obj is not SANDBOX_OBJ_SENTINEL and self.obj is not None:
            # Defensive: the only legitimate way to get into the
            # sandbox call path is via the sandbox import path.
            pass  # pragma: no cover - defensive sanity check

        msg = False
        call_str = make_call_str(o.obj_name, o.args, o.kwargs)
        error_msg = "\n" + self.wrapper.fill(
            f"Your `{o.obj_name}` malfunctioned"
            + f" when called as `{call_str}`"
            + ((o.entries) and f" with entries {o.entries}." or ".")
        )

        result = sandbox_call_obj(self.module, o)
        # Replay the worker's log into this user's LogIO so the existing
        # downstream helpers see the same characters they would in the
        # in-process path.  `interactions[0]` is always 0 (start of log);
        # the integration module reconstructs subsequent offsets.
        if result.log:
            self.log.write(result.log)
        self.interactions = list(result.interactions)
        if result.return_non_serializable:
            # Mirror the legacy behavior of capturing whatever the
            # callable returned; for non-JSON-safe returns we expose
            # the repr string so downstream comparisons can still
            # inspect it (e.g. via `assertEqual(user.returned_values,
            # "<MyObj>")`).
            self.returned_values = result.return_repr
        else:
            self.returned_values = result.return_value
        # Hand any serialized figures off to the test so plot helpers
        # (utils/plot.py) can read them via the host-side facade.  The
        # legacy path leaves `plt.gcf()` populated for the same
        # purpose; this is the sandbox equivalent.
        if result.figures:
            self.test._sandbox_figures = list(result.figures)

        outcome = classify_call_outcome(result)
        if outcome is None:
            return self.returned_values

        self.test.failureException = safe_exception_type(outcome)
        msg = self._format_sandbox_call_failure(outcome, result, error_msg)

        if msg:
            log = self.log.getvalue()
            if log:
                msg += self.format_log()
            self.test.fail(msg)

        if o.debug:
            print(self.log.getvalue())

        return self.returned_values  # pragma: no cover - unreachable after fail

    def _format_sandbox_call_failure(self, outcome, result, error_msg):
        """Format a call-phase sandbox failure as a student message.

        ExtraEntriesError gets the same "program ended before user
        finished entering input" message as the legacy path.  Anything
        else gets a synthetic traceback derived from the worker's
        structured exception chain, so the student sees the same
        information they'd see from an in-process exception.
        """
        if outcome is ExtraEntriesError:
            return (
                error_msg
                + "\n\nHint:\n"
                + self.wrapper.fill(
                    "Your program ended before the user finished entering input."
                )
            )
        # Build a traceback-style message from the worker's chain.
        chain = result.exception or []
        head = chain[0] if chain else {"type": outcome.__name__, "message": ""}
        tb_text = head.get("traceback") or ""
        formatted_traceback = (
            ("Traceback (most recent call last):\n" + tb_text) if tb_text else ""
        ) + f"{head.get('type', outcome.__name__)}: {head.get('message', '')}\n"
        from generic_grader.utils.exceptions import indent

        return indent(error_msg + "\n\n" + formatted_traceback)


class RefUser(__User__):
    def __init__(self, test, options: Options):
        self.module = options.ref_module
        super().__init__(test, options)


class SubUser(__User__):
    def __init__(self, test, options: Options):
        self.module = options.sub_module
        super().__init__(test, options)
