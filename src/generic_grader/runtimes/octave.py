"""GNU Octave runtime for generic-grader.

This runtime runs student and reference code written as ``.m`` files
inside GNU Octave via a hardened subprocess.  It is selected by setting
``Options.language = "octave"``.

Design overview
---------------

* **File location.**  ``resolve`` looks for ``<module>.m`` in the
  process's current working directory — the same directory Gradescope
  drops the student submission into, and the same directory the
  existing Python tests already switch to via ``fix_syspath``.  A
  missing file produces the same shape of error the Python runtime
  produces via :class:`Importer`: ``test.fail("Unable to import ...")``
  with a hint pointing at the expected filename.

* **Script vs. function.**  MATLAB / Octave ``.m`` files come in two
  flavours.  The test author signals which shape they want by whether
  they supply ``options.args`` / ``options.kwargs``:

  * *Script mode* (no args, no kwargs).  The file is run top-to-bottom
    — Octave executes ``<stem>`` where ``<stem>`` is the basename of
    the resolved ``.m`` file.  Reference and student files typically
    live under different stems (e.g. ``main.m`` vs ``ref_main.m``),
    so we deliberately do *not* require the two to share a stem —
    each side runs its own file.

  * *Function mode* (any args or kwargs supplied).  We call
    ``<obj_name>(<args>)`` and the file must define a function of
    that name — either as the top-of-file function of ``<stem>.m``
    or as a local/nested function inside it.  In this case
    ``obj_name`` is shared across the reference and student runs so
    the test contract is the same for both.

  This mirrors what the Python runtime does implicitly — a Python
  ``main()`` test both runs top-to-bottom (via ``__import__``) *and*
  invokes a callable.  Octave has to make the choice explicit.

* **Argument passing.**  Positional ``args`` and keyword ``kwargs`` are
  serialized into an Octave expression by :func:`_format_args`.  The
  supported types are Python's basic scalars — ``bool`` (``true`` /
  ``false``), ``int``, ``float`` (special-cased for NaN / +Inf / -Inf),
  and ``str`` (single-quoted with embedded quotes doubled per Octave's
  own rules).  Anything else raises a clear ``TypeError`` at grader
  build time, which is friendlier than an opaque parse error inside
  Octave.  Nested containers are intentionally *not* supported in the
  first pass; a follow-on PR will add them alongside the
  ``function_return_values_match_reference`` test type.

* **Sandboxing.**  The subprocess is launched with a scrubbed
  environment (``PATH``, ``HOME``, ``LANG`` only), ``--no-init-file``
  and ``--norc`` so ``~/.octaverc`` cannot influence the run, and
  POSIX resource limits set in a ``preexec_fn`` derived from the
  ``time_limit`` and ``memory_limit_GB`` fields on ``Options``.
  ``subprocess.communicate(timeout=...)`` provides a wall-clock
  backstop and — on timeout — the process group is killed so any
  child processes die with it.  This is language-independent
  sandboxing, matching the "sandbox independent of backend" design
  the extension was scoped around.

* **stdin (simulated user input).**  Anything in ``options.entries`` is
  joined with newlines and fed to the child process's stdin.  In
  Octave, ``input("prompt")`` reads from ``stdin`` when running in
  non-interactive mode with ``--eval``, which is exactly the mode we
  invoke.
"""

from __future__ import annotations

import json
import math
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from textwrap import dedent
from unittest import TestCase

import numpy as np

from generic_grader.runtimes.base import RuntimeResult
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.options import Options

# Executable name — factored out for tests.  Overriding it lets a live
# integration test skip when Octave isn't installed without special
# casing subprocess.run.
OCTAVE_EXECUTABLE = os.environ.get("OCTAVE_EXECUTABLE", "octave")

# One gigabyte in bytes.  ``options.memory_limit_GB`` is a float number
# of gigabytes; the child's ``RLIMIT_AS`` is set to that many bytes.
_GB = 1024**3


class OctaveNotInstalledError(RuntimeError):
    """Raised when the Octave executable is not on ``PATH``.

    Distinct from a student's own Octave error — this indicates a
    misconfigured grader environment and is surfaced to the test author
    (via ``test.fail``) rather than the student.
    """


class OctaveRuntimeError(RuntimeError):
    """Raised when the Octave process exits with an error.

    Carries the child's captured stderr so ``__User__.call_obj`` can
    include it in the student-facing failure message the same way it
    already includes Python tracebacks.
    """

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class OctaveTimeoutError(RuntimeError):
    """Raised when the Octave process is killed by the wall-clock
    ``time_limit`` on :class:`Options`.

    Mapped to the same student-facing "took too long" message the
    Python runtime uses via :class:`TimeoutError`.
    """


# ---------------------------------------------------------------------------
# Argument serialization
# ---------------------------------------------------------------------------
def _format_scalar(value) -> str:
    """Render a Python scalar as an Octave expression.

    The switch is deliberately exhaustive on ``type(value)`` rather
    than ``isinstance(...)``.  This means ``True`` isn't accidentally
    treated as ``1`` (Python's ``bool`` is a subclass of ``int``) —
    students should see the distinction faithfully in Octave, and
    tests are cleaner when the mapping is obvious.
    """
    t = type(value)
    if t is bool:
        return "true" if value else "false"
    if t is int:
        return str(value)
    if t is float:
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Inf" if value > 0 else "-Inf"
        # ``repr`` round-trips floats; Octave accepts the ``e`` form.
        return repr(value)
    if t is str:
        # Octave single-quoted strings escape embedded single quotes by
        # doubling them.  This is enough — single-quoted strings do not
        # interpret backslashes so we don't have to escape those.
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(
        f"Cannot serialize argument of type {t.__name__!r} to Octave. "
        "Only bool, int, float, and str are supported in this release."
    )


def _format_args(args, kwargs) -> str:
    """Produce the parenthesised argument list for an Octave call.

    Octave has no first-class ``**kwargs`` — the closest equivalent is
    passing a trailing sequence of ``('key', value)`` pairs, which
    functions like ``plot`` already use.  We adopt that convention:
    ``kwargs={'linewidth': 2}`` becomes ``, 'linewidth', 2``.  Test
    authors who need MATLAB-style optional arguments therefore get a
    natural mapping; those who don't need kwargs pay nothing.

    If ``args`` and ``kwargs`` are both empty the return value is
    ``""``, so the caller can compose ``obj_name + _format_args(...)``
    for script mode (no parens) as easily as for function mode.
    """
    parts = [_format_scalar(a) for a in args]
    for key, value in kwargs.items():
        parts.append(_format_scalar(str(key)))
        parts.append(_format_scalar(value))
    if not parts:
        return ""
    return "(" + ", ".join(parts) + ")"


# ---------------------------------------------------------------------------
# Return-value decoding
# ---------------------------------------------------------------------------
def _decode_json_value(value):
    """Convert one ``json.loads`` result into a native Python object.

    The conversion mirrors what a test author expects to compare in
    :mod:`generic_grader.function.function_return_values_match_reference`
    and the two random-return test types:

    * Scalars — ``int`` / ``float`` / ``bool`` / ``str`` — are returned
      unchanged.  Octave's ``jsonencode`` emits doubles for numeric
      scalars and ``true`` / ``false`` for ``logical`` values, so the
      ``json.loads`` mapping already produces the right Python types.
    * ``None`` (``jsonencode`` maps Octave ``[]`` to JSON ``null`` or
      ``[]``; both round-trip cleanly).  A JSON ``null`` becomes
      ``None`` — used mainly for the void-function edge case.
    * Lists — treated as Octave arrays and coerced into a
      :class:`numpy.ndarray`.  This matches the ``np.ndarray`` branch
      the ``function_return_values_match_reference`` test already uses
      for Python callables that return NumPy arrays, so reference and
      student comparisons keep the same code path.  A 1xN row vector
      in Octave (e.g. ``1:n``) round-trips through JSON as a plain
      list and lands here as a 1-D NumPy array — which is what a test
      author writing an equivalent Python reference would return.
    """
    if value is None:
        return None
    if isinstance(value, list):
        # Empty lists become 0-D empty arrays — same shape
        # ``jsonencode`` would produce for an Octave empty matrix.
        return np.array(value)
    # int / float / bool / str fall through — json.loads already produces
    # the corresponding Python type.
    return value


def _decode_returned_values(payload):
    """Decode the JSON sidecar the Octave runtime writes for a call.

    ``payload`` is either the raw JSON text or an already-parsed
    object.  The sidecar always encodes a JSON array of length
    ``nargout``:

    * length 0 → the callable produced no return value; we return
      ``None`` to match a Python function with no explicit ``return``.
    * length 1 → we unwrap the single element; Python's convention is
      that ``y = f(x)`` yields a bare value, not a 1-tuple.
    * length ≥ 2 → we return a ``tuple`` of the decoded elements,
      matching Python's own multiple-return convention.

    Kept as a module-level helper (rather than a method) so unit tests
    can exercise every branch without spinning up an Octave process.
    """
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    if not isinstance(payload, list):
        raise ValueError(
            "Octave return-value sidecar must be a JSON array; got "
            f"{type(payload).__name__}."
        )
    decoded = [_decode_json_value(v) for v in payload]
    if len(decoded) == 0:
        return None
    if len(decoded) == 1:
        return decoded[0]
    return tuple(decoded)


# ---------------------------------------------------------------------------
# Plot artifact capture
# ---------------------------------------------------------------------------
def _build_plot_capture_snippet(plot_sidecar_path: str) -> str:
    """Return an Octave snippet that serialises every open figure.

    The snippet walks every open figure and each of its non-legend
    axes, then writes a JSON payload of the shape::

        {
          "figures": [
            {
              "axes": [
                {
                  "title": ..., "xlabel": ..., "ylabel": ...,
                  "xlim": [xmin, xmax], "ylim": [ymin, ymax],
                  "xticklabels": [...], "yticklabels": [...],
                  "lines": [{"xdata": [...], "ydata": [...],
                             "color": [r, g, b]}, ...]
                },
                ...
              ]
            },
            ...
          ]
        }

    Legend axes (``tag == 'legend'``) are skipped so
    :func:`utils.octave_plot.get_property` sees only the drawing axes.
    Errors inside the snippet are swallowed (the outer ``try/catch``
    still exits 0) so a broken student figure can't wipe out an
    otherwise-passing return-value check.
    """
    escaped = plot_sidecar_path.replace("'", "''")
    return dedent(
        f"""\
        try
                gg_plot_payload__ = struct();
                gg_plot_figs__ = findall(0, 'Type', 'figure');
                gg_plot_figs__ = sort(gg_plot_figs__);
                gg_plot_figures_cell__ = {{}};
                for gg_plot_fi__ = 1:length(gg_plot_figs__)
                  gg_plot_fig__ = gg_plot_figs__(gg_plot_fi__);
                  gg_plot_axes__ = findall(gg_plot_fig__, 'Type', 'axes');
                  gg_plot_axes_cell__ = {{}};
                  for gg_plot_ai__ = 1:length(gg_plot_axes__)
                    gg_plot_ax__ = gg_plot_axes__(gg_plot_ai__);
                    if strcmp(get(gg_plot_ax__, 'tag'), 'legend')
                      continue;
                    endif
                    gg_plot_ax_payload__ = struct();
                    gg_plot_ax_payload__.title = get(get(gg_plot_ax__, 'title'), 'string');
                    gg_plot_ax_payload__.xlabel = get(get(gg_plot_ax__, 'xlabel'), 'string');
                    gg_plot_ax_payload__.ylabel = get(get(gg_plot_ax__, 'ylabel'), 'string');
                    gg_plot_ax_payload__.xlim = get(gg_plot_ax__, 'xlim');
                    gg_plot_ax_payload__.ylim = get(gg_plot_ax__, 'ylim');
                    gg_plot_xtl__ = get(gg_plot_ax__, 'xticklabel');
                    if ischar(gg_plot_xtl__)
                      gg_plot_xtl__ = cellstr(gg_plot_xtl__);
                    endif
                    gg_plot_ytl__ = get(gg_plot_ax__, 'yticklabel');
                    if ischar(gg_plot_ytl__)
                      gg_plot_ytl__ = cellstr(gg_plot_ytl__);
                    endif
                    gg_plot_ax_payload__.xticklabels = gg_plot_xtl__;
                    gg_plot_ax_payload__.yticklabels = gg_plot_ytl__;
                    gg_plot_lines__ = findobj(gg_plot_ax__, 'Type', 'line');
                    gg_plot_lines_cell__ = {{}};
                    for gg_plot_li__ = 1:length(gg_plot_lines__)
                      gg_plot_ln__ = struct();
                      gg_plot_ln__.xdata = get(gg_plot_lines__(gg_plot_li__), 'xdata');
                      gg_plot_ln__.ydata = get(gg_plot_lines__(gg_plot_li__), 'ydata');
                      gg_plot_c__ = get(gg_plot_lines__(gg_plot_li__), 'color');
                      gg_plot_ln__.color = gg_plot_c__(:)';
                      gg_plot_lines_cell__{{end+1}} = gg_plot_ln__;
                    endfor
                    gg_plot_ax_payload__.lines = gg_plot_lines_cell__;
                    gg_plot_axes_cell__{{end+1}} = gg_plot_ax_payload__;
                  endfor
                  gg_plot_fig_payload__ = struct('axes', {{gg_plot_axes_cell__}});
                  gg_plot_figures_cell__{{end+1}} = gg_plot_fig_payload__;
                endfor
                gg_plot_payload__.figures = gg_plot_figures_cell__;
                gg_plot_fid__ = fopen('{escaped}', 'w');
                fprintf(gg_plot_fid__, '%s', jsonencode(gg_plot_payload__));
                fclose(gg_plot_fid__);
              catch
                % Plot capture is best-effort — swallow so a broken
                % figure doesn't fail an otherwise-passing test.
              end_try_catch"""
    )


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
class OctaveRuntime:
    """Runtime that executes ``.m`` files under GNU Octave.

    A single instance is created per ``__User__`` (see
    :mod:`generic_grader.utils.user`); each call to :meth:`run`
    launches a fresh Octave subprocess so there is no state leakage
    between the reference run and the student run.
    """

    name = "Octave"

    # ------------------------------------------------------------------
    # resolve
    # ------------------------------------------------------------------
    def resolve(self, test: TestCase, options: Options, module: str):
        """Verify ``<module>.m`` exists in the current working directory.

        Returns the absolute path to the file as the opaque *handle*
        that :meth:`run` will consume.  On failure we call
        ``test.fail(...)`` with a message shaped like the Python
        runtime's "Unable to import" text, so students see a
        consistent style regardless of language.
        """
        path = os.path.abspath(module + ".m")
        if not os.path.isfile(path):
            wrapper = get_wrapper()
            msg = (
                "\n"
                + wrapper.fill(f"Unable to load `{module}.m`.")
                + "\n\nHint:\n"
                + wrapper.fill(
                    f"Make sure you have submitted a file named `{module}.m` "
                    "in the top level of your submission."
                )
            )
            test.failureException = FileNotFoundError
            test.fail(msg)
        return path

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------
    def run(
        self,
        options: Options,
        handle,
        log,
        entries,
    ) -> RuntimeResult:
        """Invoke the resolved ``.m`` under Octave.

        Writes captured stdout into ``log`` (respecting its optional
        ``log_limit``), pipes ``entries`` to stdin, enforces
        ``time_limit`` / ``memory_limit_GB`` via the preexec hook, and
        raises :class:`OctaveRuntimeError`,
        :class:`OctaveTimeoutError`, or
        :class:`OctaveNotInstalledError` on failure — all three of
        which the caller in :mod:`generic_grader.utils.user` renders
        into student-facing messages.
        """
        # `handle` is the resolved .m path.  We invoke Octave with the
        # containing directory added to the front of the load path, and
        # cd into it, so both scripts and function files with names
        # that don't happen to match Octave's own path get found.
        script_dir = os.path.dirname(handle)
        stem = os.path.splitext(os.path.basename(handle))[0]

        executable = shutil.which(OCTAVE_EXECUTABLE)
        if executable is None:
            raise OctaveNotInstalledError(
                f"The Octave executable ({OCTAVE_EXECUTABLE!r}) was not "
                "found on PATH. Install GNU Octave on the grader host, or "
                "set the OCTAVE_EXECUTABLE environment variable to its "
                "absolute path."
            )

        # Function-mode calls ask Octave to write the return values to a
        # temp file so we can decode them back into Python.  Script mode
        # (no args, no kwargs) skips the sidecar entirely — there is no
        # single value to capture, and the log-based tests are the
        # ones that consume script-mode output.
        is_script = not options.args and not options.kwargs
        sidecar_path: str | None = None
        isolated_dir: str | None = None
        # Always allocate a plot sidecar; the harness inside the child
        # writes it after the student code runs so that plot tests can
        # compare properties without matplotlib.  ``run`` cleans it up
        # in the ``finally`` below, whether or not any figures existed.
        fd, plot_sidecar_path = tempfile.mkstemp(
            prefix="gg_octave_plot_", suffix=".json"
        )
        os.close(fd)
        if not is_script:
            # ``delete=False`` because Octave, not Python, writes the
            # file — we open, close, and hand the path across the
            # process boundary.  The ``finally`` at the end of ``run``
            # removes it.
            fd, sidecar_path = tempfile.mkstemp(
                prefix="gg_octave_return_", suffix=".json"
            )
            os.close(fd)

            # In function mode we need Octave to find the resolved
            # ``handle`` file by ``obj_name`` — not by its own stem
            # (which may be ``ref_<obj_name>``).  Copy it into a
            # private per-invocation directory renamed as
            # ``<obj_name>.m`` and run there, so ref and student
            # runs never see each other's files even when they share
            # the same submission directory.  This is what makes the
            # ``@reference_test`` swap correct for Octave, where
            # function lookup is by file stem rather than by module
            # namespace.
            isolated_dir = tempfile.mkdtemp(prefix="gg_octave_run_")
            isolated_path = os.path.join(isolated_dir, f"{options.obj_name}.m")
            shutil.copyfile(handle, isolated_path)
            script_dir = isolated_dir
            stem = options.obj_name

        eval_expr = self._build_eval_expression(
            options, stem, sidecar_path, plot_sidecar_path
        )
        argv = [
            executable,
            "--no-gui",
            "--norc",
            "--no-init-file",
            "--quiet",
            "--eval",
            eval_expr,
        ]

        stdin_bytes = self._build_stdin(entries)
        env = self._safe_env()
        preexec = self._make_preexec_fn(options)

        try:
            try:
                proc = subprocess.Popen(  # noqa: S603 — argv is a fixed list, not shell
                    argv,
                    cwd=script_dir,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    preexec_fn=preexec,
                    start_new_session=True,
                )
            except FileNotFoundError as e:
                # Race: which() found the executable a moment ago but it
                # vanished before exec.  Convert to the same
                # not-installed error the up-front check produces.
                raise OctaveNotInstalledError(str(e)) from e

            try:
                stdout_bytes, stderr_bytes = proc.communicate(
                    input=stdin_bytes, timeout=options.time_limit
                )
            except subprocess.TimeoutExpired:
                # Kill the whole process group so any children spawned by
                # a runaway `.m` file die with it.  This mirrors what the
                # Python runtime's SIGALRM-based time_limit does.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:  # pragma: no cover — race
                    pass
                # Drain what we have so the caller can still show partial
                # output in the log; ignore any decode errors here.
                try:
                    stdout_bytes, _ = proc.communicate(timeout=1)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    stdout_bytes = b""
                self._tee_to_log(stdout_bytes, log)
                raise OctaveTimeoutError(
                    f"Your `{options.obj_name}` took longer than "
                    f"{options.time_limit} second(s) and was terminated."
                )

            self._tee_to_log(stdout_bytes, log)
            if proc.returncode != 0:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")
                raise OctaveRuntimeError(
                    f"Octave exited with code {proc.returncode} while running "
                    f"`{options.obj_name}`.",
                    stderr=stderr_text,
                )

            returned = self._read_sidecar(sidecar_path)
            plot_artifact = self._read_plot_sidecar(plot_sidecar_path)
            artifacts: dict = {}
            if plot_artifact is not None:
                artifacts["plot"] = plot_artifact
            return RuntimeResult(returned_values=returned, artifacts=artifacts)
        finally:
            # Always try to clean up the sidecars — including on early
            # exceptions above.  Ignore "already gone" races.
            if sidecar_path is not None:
                try:
                    os.unlink(sidecar_path)
                except FileNotFoundError:  # pragma: no cover — race
                    pass
            try:
                os.unlink(plot_sidecar_path)
            except FileNotFoundError:  # pragma: no cover — race
                pass
            if isolated_dir is not None:
                shutil.rmtree(isolated_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_eval_expression(
        options: Options,
        stem: str,
        sidecar_path: str | None = None,
        plot_sidecar_path: str | None = None,
    ) -> str:
        """Construct the ``--eval`` argument for the Octave subprocess.

        Two shapes:

        * **Script mode** (empty args and kwargs).  The eval expression
          is just the file's stem, which causes Octave to run the file
          top-to-bottom.  The stem is used verbatim so reference and
          student files with different stems (e.g. ``ref_main.m`` and
          ``main.m``) each execute their own contents.

        * **Function mode** (any args or kwargs supplied).  We call
          ``<obj_name>(<serialized args>)``.  The function must exist
          as either the top-of-file function of ``<stem>.m`` or as a
          subfunction inside it — Octave's usual name-resolution
          applies.  When ``sidecar_path`` is supplied, we also ask
          Octave to introspect the callable's ``nargout``, capture
          every return value into a cell, and ``jsonencode`` the
          result to that path so the parent process can decode it.

        We prefix both with an ``addpath`` for the script directory in
        case the caller's CWD differs from the file's directory (belt
        and braces — we also ``cd`` there via ``Popen(cwd=...)``).
        The ``try / catch`` wrapper turns any uncaught Octave error
        into a nonzero exit code with the message on stderr, which
        maps cleanly onto :class:`OctaveRuntimeError`.
        """
        # Script mode is signalled by an empty args/kwargs.  Because
        # the reference and student files typically have different
        # stems (e.g. ``ref_main.m`` vs ``main.m``), script mode runs
        # the file's actual stem, not ``obj_name`` — that way the
        # same ``Options.obj_name`` (used for error messages and
        # docstring generation) works for both sides.
        is_script = not options.args and not options.kwargs
        # ``stem`` and ``obj_name`` come from Options; they are the
        # student's filename / function name, so we deliberately do
        # not quote them (they must be valid Octave identifiers).
        if is_script:
            body = f"{stem};"
        else:
            arg_expr = _format_args(options.args, options.kwargs)
            if sidecar_path is None:
                # Kept for internal use / tests that don't want a
                # sidecar; production ``run`` always passes one.
                body = f"{options.obj_name}{arg_expr};"
            else:
                # ``nargout`` returns the fixed output count for named
                # functions or ``-1`` for varargout — in the latter
                # case we conservatively capture one output, which is
                # the overwhelmingly common ``y = f(x)`` shape.  We
                # single-quote the sidecar path with Octave's
                # doubled-quote escape rule so paths containing quotes
                # (rare, but possible in ``TMPDIR``) still parse.
                escaped_path = sidecar_path.replace("'", "''")
                body = (
                    f"gg_nout__ = nargout('{options.obj_name}');\n"
                    f"              if (gg_nout__ < 0); gg_nout__ = 1; endif\n"
                    f"              if (gg_nout__ == 0)\n"
                    f"                {options.obj_name}{arg_expr};\n"
                    f"                gg_ret__ = {{}};\n"
                    f"              else\n"
                    f"                gg_ret__ = cell(1, gg_nout__);\n"
                    f"                [gg_ret__{{1:gg_nout__}}] = "
                    f"{options.obj_name}{arg_expr};\n"
                    f"              endif\n"
                    f"              gg_fid__ = fopen('{escaped_path}', 'w');\n"
                    f"              fprintf(gg_fid__, '%s', "
                    f"jsonencode(gg_ret__));\n"
                    f"              fclose(gg_fid__);"
                )
        # When a plot sidecar is requested (production ``run`` always
        # requests one), we force the ``gnuplot`` toolkit and hidden
        # figures so tests never require an X server, and we emit a
        # capture harness after the student body that writes the JSON
        # payload consumed by :func:`_read_plot_sidecar`.  The header
        # runs unconditionally — even student code that never touches
        # plots is safe because setting a default toolkit is a no-op
        # when no figure is created.
        header = ""
        capture = ""
        if plot_sidecar_path is not None:
            header = (
                "graphics_toolkit('gnuplot');\n"
                "              set(0, 'DefaultFigureVisible', 'off');\n"
                "              "
            )
            capture = "\n              " + _build_plot_capture_snippet(
                plot_sidecar_path
            )
        return dedent(
            f"""\
            try
              addpath(pwd);
              {header}{body}{capture}
            catch err
              fprintf(stderr, '%s\\n', err.message);
              exit(1);
            end_try_catch
            exit(0);
            """
        )

    @staticmethod
    def _read_plot_sidecar(plot_sidecar_path: str):
        """Read the JSON sidecar the plot-capture harness wrote.

        Returns the parsed dictionary payload on success — shaped like
        ``{"figures": [{"axes": [{...}, ...]}, ...]}`` — or ``None`` when
        the file is missing, empty, or unparseable.  Silence on decode
        failure is deliberate: plot capture is best-effort, and a
        malformed payload should degrade to a clear "no plot artifact"
        message from the test rather than blowing up the run.
        """
        try:
            with open(plot_sidecar_path, encoding="utf-8") as handle:
                text = handle.read()
        except FileNotFoundError:
            return None
        if not text.strip():
            return None
        try:
            return json.loads(text)
        except (ValueError, json.JSONDecodeError):  # pragma: no cover — defensive
            return None

    @staticmethod
    def _read_sidecar(sidecar_path: str | None):
        """Read and decode the return-value sidecar Octave wrote.

        Returns ``None`` when ``sidecar_path`` is ``None`` (script mode)
        or when the file is missing / empty — the latter is not an
        error, it simply means the callable didn't produce anything
        we can capture.  Any other decoding failure surfaces as an
        :class:`OctaveRuntimeError` so the student sees a clear
        "return value could not be captured" message instead of a
        traceback deep inside :mod:`json`.
        """
        if sidecar_path is None:
            return None
        try:
            with open(sidecar_path, encoding="utf-8") as handle:
                text = handle.read()
        except FileNotFoundError:
            return None
        if not text.strip():
            return None
        try:
            return _decode_returned_values(text)
        except (ValueError, json.JSONDecodeError) as e:
            raise OctaveRuntimeError(
                "Could not decode the return value(s) produced by Octave. "
                f"Raw payload: {text!r}",
                stderr=str(e),
            ) from e

    @staticmethod
    def _build_stdin(entries) -> bytes:
        """Encode ``entries`` as a newline-terminated stdin payload.

        ``entries`` may be an iterator (the caller passes
        ``self.entries``); we materialize it into a list here so the
        subprocess sees every entry even if the iterator has already
        been partially advanced.
        """
        materialized = list(entries)
        if not materialized:
            return b""
        return ("\n".join(str(e) for e in materialized) + "\n").encode("utf-8")

    @staticmethod
    def _safe_env() -> dict[str, str]:
        """Return a minimal, scrubbed environment for the Octave subprocess.

        We only forward variables Octave actually needs to start —
        ``PATH`` (to find its own shared libraries), ``HOME``
        (Octave writes a history file even in non-interactive mode),
        ``LANG`` / ``LC_ALL`` (locale), and ``OCTAVE_HISTFILE=/dev/null``
        so we don't accidentally leak state between the reference and
        student runs.  Everything else — including any grader-side
        ``PYTHONPATH``, tokens, or CI secrets — is dropped.
        """
        allow = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        env = {k: v for k, v in os.environ.items() if k in allow}
        # Belt and braces: even with --no-init-file / --norc, Octave
        # will still touch ~/.octave_hist unless we redirect it.
        env["OCTAVE_HISTFILE"] = "/dev/null"
        return env

    @staticmethod
    def _make_preexec_fn(options: Options):
        """Build a ``preexec_fn`` that applies POSIX resource limits.

        ``preexec_fn`` runs in the child between ``fork`` and ``exec``,
        so raising in it kills the child before Octave starts.  We
        clamp memory (``RLIMIT_AS``), CPU seconds (``RLIMIT_CPU``),
        maximum file size the child can create (``RLIMIT_FSIZE`` at 64
        MiB — plenty for a student output file, but small enough to
        stop accidental infinite loops from filling the disk), and the
        number of open file descriptors (``RLIMIT_NOFILE``).

        The CPU limit is set 1 second above ``time_limit`` so the
        wall-clock timeout (``communicate(timeout=...)``) can fire
        first and produce our nicer :class:`OctaveTimeoutError`
        message; the ``RLIMIT_CPU`` acts as a hard floor if the
        parent is somehow unable to kill the group.
        """
        mem_bytes = max(1, int(options.memory_limit_GB * _GB))
        cpu_seconds = max(1, int(options.time_limit) + 1)

        def preexec():  # pragma: no cover — runs post-fork
            # RLIMIT_AS: total virtual memory.  Same knob Python
            # runtime uses via `resource.setrlimit` in
            # `resource_limits.memory_limit`.
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

        # On non-POSIX platforms `resource` might be unavailable; the
        # runtime is POSIX-only by design (Gradescope + typical dev
        # boxes), and this refusal-to-boot is intentional so the
        # limits can't be silently skipped.
        if sys.platform == "win32":  # pragma: no cover — POSIX-only
            raise OctaveNotInstalledError(
                "The Octave runtime requires a POSIX host (Linux or macOS)."
            )
        return preexec

    @staticmethod
    def _tee_to_log(stdout_bytes: bytes, log) -> None:
        """Write captured stdout into ``log``.

        Decodes as UTF-8 with a replacement fallback (Octave's stdout
        may legitimately contain non-UTF-8 bytes if the student
        printed a raw uint8 array — we don't want that to crash the
        grader).  Respects the log's optional character limit — the
        same :class:`~generic_grader.utils.exceptions.LogLimitExceededError`
        that fires for Python code fires here too.
        """
        if not stdout_bytes:
            return
        text = stdout_bytes.decode("utf-8", errors="replace")
        log.write(text)


__all__ = (
    "OctaveNotInstalledError",
    "OctaveRuntime",
    "OctaveRuntimeError",
    "OctaveTimeoutError",
)
