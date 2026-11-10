"""GNU Octave runtime for generic-grader.

This runtime runs student and reference code written as ``.m`` files
inside GNU Octave in a resource-limited subprocess.  It is selected by
setting ``Options.language = "octave"``.  See the *Limits* note below
for what that does and does not protect.

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
    ``<obj_name>(<args>)``.  Each file runs from a private copy in a
    temporary directory (see :meth:`OctaveRuntime._stage_run`)
    so the reference never shadows, or runs, the student's file.  If
    ``obj_name`` is the stem of ``sub_module`` it names the file's
    primary function, and the reference's primary function is called
    under the same name.  Otherwise it names a subfunction, and the
    file is loaded as a script so the subfunction can be reached; that
    needs every function in the file to end with ``end`` or
    ``endfunction``.  Other ``.m`` files next to the submission are
    copied too, so helper functions are found.

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

* **Limits.**  What is enforced:

  * a scrubbed environment (``PATH``, ``HOME``, ``LANG``, ``LC_ALL``,
    ``LD_LIBRARY_PATH`` and ``TMPDIR`` are forwarded; ``OCTAVE_HISTFILE``,
    ``OPENBLAS_NUM_THREADS`` and ``OMP_NUM_THREADS`` are pinned);
  * ``--no-init-file`` and ``--norc``, so ``~/.octaverc`` is ignored;
  * ``RLIMIT_AS`` (``memory_limit_GB``), ``RLIMIT_CPU``
    (``time_limit`` + 1 s), ``RLIMIT_FSIZE`` and ``RLIMIT_NOFILE``,
    applied by the ``_LAUNCHER`` bootstrap before Octave is exec'd;
  * stdout and stderr captured in temp files bounded by
    ``RLIMIT_FSIZE``; reaching the bound is an error;
  * a wall-clock ``time_limit``, and a ``SIGKILL`` of the whole process
    group on every exit path.

  What is **not** enforced: there is no network or process isolation,
  and no filesystem isolation unless the grader runs as root.  Then the
  student's code runs as an unprivileged user in a private copy of the
  submission (see :mod:`generic_grader.runtimes.sandbox`); the reference
  and test files must be unreadable by that user.  Otherwise student
  ``.m`` code can run shell commands with ``system()`` and read any file
  the grader user can read, including the reference solution and test
  files.

* **stdin (simulated user input).**  Anything in ``options.entries`` is
  joined with newlines and fed to the child process's stdin.  In
  Octave, ``input("prompt")`` reads from ``stdin`` when running in
  non-interactive mode with ``--eval``, which is exactly the mode we
  invoke.
"""

from __future__ import annotations

import errno
import glob
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from textwrap import dedent
from unittest import TestCase

import numpy as np

from generic_grader.runtimes.base import (
    RuntimeExecutionError,
    RuntimeResult,
    RuntimeTimeoutError,
    RuntimeUnavailableError,
)
from generic_grader.runtimes.sandbox import (
    Sandbox,
    can_read,
    kill_all_processes,
    resolve_sandbox,
    submission_dir,
)
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.exceptions import LogLimitExceededError
from generic_grader.utils.options import Options

# Executable name, read once at import time; changing the environment
# variable afterwards has no effect.
OCTAVE_EXECUTABLE = os.environ.get("OCTAVE_EXECUTABLE", "octave")

# One gigabyte in bytes.  ``options.memory_limit_GB`` is a float number
# of gigabytes; the child's ``RLIMIT_AS`` is set to that many bytes.
_GB = 1024**3

# stem and obj_name are interpolated unquoted into the eval string.
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Maximum size in bytes of each captured output file.  Applied as
# RLIMIT_FSIZE by the launcher and used to detect overflow after the
# child exits — Octave catches SIGXFSZ itself, so writes past the
# limit are silently truncated instead of killing the process.
FILE_SIZE_LIMIT = 64 * 1024 * 1024

# Child-side bootstrap run as `python -I -c _LAUNCHER <mem> <cpu>
# <octave argv...>`: applies the four rlimits, then execs Octave in
# the same process so proc.pid stays Octave's pid (killpg keeps
# working).  preexec_fn would be unsafe in a multithreaded parent.
_LAUNCHER = f"""import os, resource, sys
_mem = int(sys.argv[1])
_cpu = int(sys.argv[2])
resource.setrlimit(resource.RLIMIT_AS, (_mem, _mem))
resource.setrlimit(resource.RLIMIT_CPU, (_cpu, _cpu))
resource.setrlimit(resource.RLIMIT_FSIZE, ({FILE_SIZE_LIMIT}, {FILE_SIZE_LIMIT}))
resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
os.execv(sys.argv[3], sys.argv[3:])
"""


class OctaveNotInstalledError(RuntimeUnavailableError):
    """Raised when the Octave executable is not on ``PATH``.

    Distinct from a student's own Octave error — this indicates a
    misconfigured grader environment and is surfaced to the test author
    (via ``test.fail``) rather than the student.
    """


class OctaveRuntimeError(RuntimeExecutionError):
    """Raised when the Octave process exits with an error.

    Carries the child's captured stderr so ``__User__.call_obj`` can
    include it in the student-facing failure message the same way it
    already includes Python tracebacks.
    """


class OctaveTimeoutError(RuntimeTimeoutError):
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
        raise ValueError(  # noqa: TRY004 — malformed data, not a wrong argument type
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

        Raises :class:`ValueError` if ``module`` is not a valid Octave
        identifier; that is a grader misconfiguration, not a student error.
        """
        stem = os.path.basename(module)
        if not IDENTIFIER_RE.fullmatch(stem):
            raise ValueError(
                f"Octave module name {module!r} must be a valid identifier "
                "(letters, digits and underscores, not starting with a digit)."
            )
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
        ``time_limit`` / ``memory_limit_GB`` via the rlimit launcher,
        and raises :class:`OctaveRuntimeError`,
        :class:`OctaveTimeoutError`, or
        :class:`OctaveNotInstalledError` on failure — all three of
        which the caller in :mod:`generic_grader.utils.user` renders
        into student-facing messages.
        """
        if sys.platform == "win32":  # pragma: no cover — POSIX-only
            raise OctaveNotInstalledError(
                "The Octave runtime requires a POSIX host (Linux or macOS)."
            )

        executable = shutil.which(OCTAVE_EXECUTABLE)
        if executable is None:
            raise OctaveNotInstalledError(
                f"The Octave executable ({OCTAVE_EXECUTABLE!r}) was not "
                "found on PATH. Install GNU Octave on the grader host, or "
                "set the OCTAVE_EXECUTABLE environment variable to its "
                "absolute path."
            )

        mem_bytes = max(1, int(options.memory_limit_GB * _GB))
        cpu_seconds = max(1, int(options.time_limit) + 1)

        # Function-mode calls ask Octave to write the return values to a
        # temp file so we can decode them back into Python.  Script mode
        # (no args, no kwargs) skips the sidecar entirely — there is no
        # single value to capture, and the log-based tests are the
        # ones that consume script-mode output.
        is_script = not options.args and not options.kwargs
        sandbox = self._sandbox_for(options, handle)
        submitted_dir = None
        if sandbox is not None:
            submitted_dir = submission_dir()
            self._require_reference_hidden(sandbox, options)
        # Without a sandbox, script mode runs in the file's own directory,
        # which puts it on Octave's load path, and function mode runs from a
        # private copy.  A sandboxed run always uses a private copy.
        script_dir = os.path.dirname(handle)
        stem = os.path.splitext(os.path.basename(handle))[0]
        sidecar_path: str | None = None
        stage_dir: str | None = None
        source_path: str | None = None
        plot_sidecar_path: str | None = None
        try:
            if sandbox is not None or not is_script:
                stage_dir, source_path = self._stage_run(
                    options, handle, is_script=is_script, submitted_dir=submitted_dir
                )
                script_dir = stage_dir
            # Sidecars live in the staging directory of a sandboxed run so
            # the sandbox user can write them.
            if not is_script:
                # Octave, not Python, writes the file, so it is created
                # here and the path handed across the process boundary.
                fd, sidecar_path = tempfile.mkstemp(
                    prefix="gg_octave_return_",
                    suffix=".json",
                    dir=stage_dir if sandbox else None,
                )
                os.close(fd)

            # The harness inside the child writes the plot sidecar after the
            # student code runs, so plot tests need no matplotlib.
            fd, plot_sidecar_path = tempfile.mkstemp(
                prefix="gg_octave_plot_",
                suffix=".json",
                dir=stage_dir if sandbox else None,
            )
            os.close(fd)
            if sandbox is not None:
                self._hand_over(sandbox, stage_dir)

            eval_expr = self._build_eval_expression(
                options, stem, sidecar_path, plot_sidecar_path, source_path
            )
            argv = [
                sys.executable,
                "-I",
                "-c",
                _LAUNCHER,
                str(mem_bytes),
                str(cpu_seconds),
                executable,
                "--no-gui",
                "--norc",
                "--no-init-file",
                "--quiet",
                "--eval",
                eval_expr,
            ]

            stdin_bytes = self._build_stdin(entries)
            env = self._safe_env(stage_dir if sandbox else None)
            identity = (
                {"user": sandbox.uid, "group": sandbox.gid, "extra_groups": []}
                if sandbox
                else {}
            )

            # Child output goes to disk-backed temp files (bounded by
            # RLIMIT_FSIZE) instead of unbounded in-memory pipes.
            with (
                tempfile.TemporaryFile() as out_file,
                tempfile.TemporaryFile() as err_file,
            ):
                try:
                    proc = subprocess.Popen(
                        argv,
                        cwd=script_dir,
                        stdin=subprocess.PIPE,
                        stdout=out_file,
                        stderr=err_file,
                        env=env,
                        start_new_session=True,
                        **identity,
                    )
                except FileNotFoundError as e:
                    # Race: which() found the executable a moment ago but it
                    # vanished before exec.  Convert to the same
                    # not-installed error the up-front check produces.
                    raise OctaveNotInstalledError(str(e)) from e
                except PermissionError as e:
                    raise RuntimeUnavailableError(
                        f"Could not start Octave as uid {identity.get('user')}: "
                        f"{e}. The Python interpreter and Octave must be "
                        "executable by that user, and the grader needs "
                        "permission to switch to it."
                    ) from e

                try:
                    proc.communicate(input=stdin_bytes, timeout=options.time_limit)
                except subprocess.TimeoutExpired:
                    self._reap_group(proc, sandbox)
                    out_bytes, err_bytes = self._read_captures(out_file, err_file)
                    self._raise_if_output_overflow(options, out_bytes, err_bytes)
                    # The timeout error must win over a log-limit error.
                    try:
                        self._tee_to_log(out_bytes, log)
                    except LogLimitExceededError:
                        pass
                    raise OctaveTimeoutError(
                        f"Your `{options.obj_name}` took longer than "
                        f"{options.time_limit} second(s) and was terminated."
                    )
                except Exception:
                    self._reap_group(proc, sandbox)
                    raise

                self._reap_group(proc, sandbox)
                out_bytes, err_bytes = self._read_captures(out_file, err_file)
                self._raise_if_output_overflow(options, out_bytes, err_bytes)
                self._tee_to_log(out_bytes, log)
                if proc.returncode != 0:
                    stderr = err_bytes.decode("utf-8", errors="replace")
                    if source_path and "nested functions not implemented" in stderr:
                        stderr += (
                            "\nEnd every function in the file with `end` or "
                            "`endfunction` so a subfunction can be called."
                        )
                    raise OctaveRuntimeError(
                        f"Octave exited with code {proc.returncode} while running "
                        f"`{options.obj_name}`.",
                        stderr=stderr,
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
            if stage_dir is not None:
                shutil.rmtree(stage_dir, ignore_errors=True)
            if plot_sidecar_path is not None:
                try:
                    os.unlink(plot_sidecar_path)
                except FileNotFoundError:  # pragma: no cover — race
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _sandbox_for(options: Options, handle: str) -> Sandbox | None:
        """Return the identity to run ``handle`` as, or ``None`` to not drop.

        The reference is trusted and runs as the grader.  Anything not
        known to be the reference is treated as student code.
        """
        reference = os.path.abspath(options.ref_module + ".m")
        if options.ref_module != options.sub_module and (
            os.path.abspath(handle) == reference
        ):
            return None
        return resolve_sandbox()

    @staticmethod
    def _require_reference_hidden(sandbox: Sandbox, options: Options) -> None:
        """Fail closed if the sandbox user could read the reference file."""
        reference = os.path.abspath(options.ref_module + ".m")
        if os.path.exists(reference) and can_read(sandbox, reference):
            raise RuntimeUnavailableError(
                f"The sandbox user (uid {sandbox.uid}) can read the reference "
                f"solution {reference!r}. Make the directory that holds it "
                "(and the test files) accessible to the grader only, e.g. "
                "`chmod 700 /autograder/source`."
            )

    @staticmethod
    def _hand_over(sandbox: Sandbox, stage_dir: str) -> None:
        """Make the sandbox user the sole owner of the staging directory."""
        os.chmod(stage_dir, 0o700)
        os.lchown(stage_dir, sandbox.uid, sandbox.gid)
        for root, dirs, files in os.walk(stage_dir):
            for name in (*dirs, *files):
                os.lchown(os.path.join(root, name), sandbox.uid, sandbox.gid)

    @staticmethod
    def _copy_submission(src_dir: str, stage_dir: str, sides: set[str]) -> None:
        """Copy everything the student submitted into ``stage_dir``.

        Symlinks in the submission are never followed, because the grader
        reads the files as a privileged user.
        """
        for entry in os.scandir(src_dir):
            if entry.is_symlink():
                continue
            target = os.path.join(stage_dir, entry.name)
            if entry.is_dir():
                shutil.copytree(entry.path, target, symlinks=True)
            elif entry.is_file() and not (
                entry.name.endswith(".m") and entry.name[:-2] in sides
            ):
                shutil.copy2(entry.path, target)

    @staticmethod
    def _copy_provided(options: Options, stage_dir: str) -> None:
        """Copy the grader-supplied input files the student's code may read."""
        for pattern in options.provided_files:
            for path in glob.glob(pattern):
                target = os.path.join(stage_dir, os.path.basename(path))
                if os.path.isdir(path):
                    shutil.copytree(path, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(path, target)

    @staticmethod
    def _stage_run(
        options: Options,
        handle: str,
        *,
        is_script: bool,
        submitted_dir: str | None = None,
    ) -> tuple[str, str | None]:
        """Copy ``handle`` into a fresh directory to run it from.

        Octave resolves ``foo(...)`` by file name, so the reference
        (``ref_foo.m``) and student (``foo.m``) files would shadow each
        other if run side by side.  The directory holds the other ``.m``
        files from the submission directory, except the two sides' own
        files, so helper functions are still found, plus
        ``options.provided_files``.

        With ``submitted_dir`` (a sandboxed student run) the directory
        instead holds everything the student submitted plus
        ``options.provided_files``, and nothing else from the grader's
        directory.

        Returns ``(stage_dir, source_path)``.  ``source_path`` is ``None``
        unless ``obj_name`` names a subfunction.  Otherwise it is the staged
        copy to ``source`` as a script, which is the only way to call a
        subfunction from outside its file.  A script is staged under its own
        name.
        """
        handle_stem = os.path.splitext(os.path.basename(handle))[0]
        sub_stem = os.path.basename(options.sub_module)
        sides = {handle_stem, sub_stem, os.path.basename(options.ref_module)}

        stage_dir = tempfile.mkdtemp(prefix="gg_octave_run_")
        try:
            if submitted_dir is not None:
                OctaveRuntime._copy_submission(submitted_dir, stage_dir, sides)
                OctaveRuntime._copy_provided(options, stage_dir)
            else:
                src_dir = os.path.dirname(handle)
                for name in os.listdir(src_dir):
                    path = os.path.join(src_dir, name)
                    if (
                        name.endswith(".m")
                        and name[:-2] not in sides
                        and os.path.isfile(path)
                    ):
                        shutil.copy2(path, stage_dir)
                OctaveRuntime._copy_provided(options, stage_dir)
            if is_script:
                shutil.copy2(handle, os.path.join(stage_dir, handle_stem + ".m"))
                return stage_dir, None
            if options.obj_name in (sub_stem, handle_stem):
                shutil.copy2(handle, os.path.join(stage_dir, options.obj_name + ".m"))
                return stage_dir, None
            # A leading ``1;`` makes Octave treat the file as a script, so
            # its functions are defined for the caller.  Same line, so
            # error line numbers are unchanged.
            staged = os.path.join(stage_dir, handle_stem + ".m")
            with open(handle, "rb") as src, open(staged, "wb") as dst:
                dst.write(b"1; " + src.read())
            return stage_dir, staged
        except BaseException:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise

    @staticmethod
    def _build_eval_expression(
        options: Options,
        stem: str,
        sidecar_path: str | None = None,
        plot_sidecar_path: str | None = None,
        source_path: str | None = None,
    ) -> str:
        """Construct the ``--eval`` argument for the Octave subprocess.

        Two shapes:

        * **Script mode** (empty args and kwargs).  The eval expression
          is just the file's stem, which causes Octave to run the file
          top-to-bottom.  The stem is used verbatim so reference and
          student files with different stems (e.g. ``ref_main.m`` and
          ``main.m``) each execute their own contents.

        * **Function mode** (any args or kwargs supplied).  We call
          ``<obj_name>(<serialized args>)``.  When ``source_path`` is
          given, that script is ``source``d first so a subfunction of
          the file is defined (see :meth:`_stage_run`).  When
          ``sidecar_path`` is supplied, we also ask Octave to introspect
          the callable's ``nargout``, capture every return value into a
          cell, and ``jsonencode`` the result to that path so the parent
          process can decode it.

        The file's directory is on Octave's path because ``Popen`` runs
        it with that directory as its cwd.  The ``try / catch`` wrapper
        turns any uncaught Octave error into a nonzero exit code with
        the message on stderr, which maps cleanly onto
        :class:`OctaveRuntimeError`.
        """
        # Script mode is signalled by an empty args/kwargs.  Because
        # the reference and student files typically have different
        # stems (e.g. ``ref_main.m`` vs ``main.m``), script mode runs
        # the file's actual stem, not ``obj_name`` — that way the
        # same ``Options.obj_name`` (used for error messages and
        # docstring generation) works for both sides.
        is_script = not options.args and not options.kwargs
        # Not quoted: ``resolve`` and ``Options`` validate both as identifiers.
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
        if source_path and not is_script:
            escaped_source = source_path.replace("'", "''")
            body = f"source('{escaped_source}'); {body}"
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
              {header}{body}{capture}
            catch err
              fprintf(stderr, '%s\\n', err.message);
              exit(1);
            end_try_catch
            exit(0);
            """
        )

    @staticmethod
    def _read_text_nofollow(path: str) -> str | None:
        """Read a file that student code may have replaced.

        Returns ``None`` if it is missing.  Raises :class:`OSError` if it
        is not a regular file, e.g. a symlink to a file only the grader can
        read, or a FIFO that would block the read.
        """
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, encoding="utf-8", errors="replace") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise OSError(errno.EINVAL, "Not a regular file", path)
            return handle.read()

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
            text = OctaveRuntime._read_text_nofollow(plot_sidecar_path)
        except OSError:
            return None
        if text is None or not text.strip():
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
            text = OctaveRuntime._read_text_nofollow(sidecar_path)
        except OSError as e:
            raise OctaveRuntimeError(
                "Could not read the return value(s) produced by Octave.",
                stderr=str(e),
            ) from e
        if text is None or not text.strip():
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
    def _safe_env(scratch_dir: str | None = None) -> dict[str, str]:
        """Return a minimal, scrubbed environment for the Octave subprocess.

        We only forward variables Octave actually needs to start —
        ``PATH`` (to find its own shared libraries), ``HOME``
        (Octave writes a history file even in non-interactive mode),
        ``LANG`` / ``LC_ALL`` (locale), ``LD_LIBRARY_PATH`` (installs in
        a non-standard prefix), and ``OCTAVE_HISTFILE=/dev/null``
        so we don't accidentally leak state between the reference and
        student runs.  Everything else — including any grader-side
        ``PYTHONPATH``, tokens, or CI secrets — is dropped.
        """
        allow = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "LD_LIBRARY_PATH")
        env = {k: v for k, v in os.environ.items() if k in allow}
        # Belt and braces: even with --no-init-file / --norc, Octave
        # will still touch ~/.octave_hist unless we redirect it.
        env["OCTAVE_HISTFILE"] = "/dev/null"
        # OpenBLAS spawns one thread per core, which aborts under RLIMIT_AS.
        env["OPENBLAS_NUM_THREADS"] = "1"
        env["OMP_NUM_THREADS"] = "1"
        if scratch_dir is not None:
            # The sandbox user cannot write the grader's HOME or TMPDIR.
            env["HOME"] = env["TMPDIR"] = scratch_dir
        return env

    @staticmethod
    def _reap_group(proc, sandbox: Sandbox | None = None) -> None:
        """SIGKILL the child's process group and reap the child.

        Called on every exit path (normal, nonzero, timeout,
        exception) so grandchildren backgrounded via ``system()``
        cannot outlive the run.  A dedicated sandbox user also loses every
        process it owns, which catches children that left the group.
        """
        pid = getattr(proc, "pid", None)
        # killpg(1, sig) is kill(-1, sig): it signals every process we may
        # signal, so a non-int pid (e.g. an unconfigured mock) must not reach it.
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        if sandbox is not None and sandbox.dedicated:
            kill_all_processes(sandbox)

    @staticmethod
    def _read_captures(out_file, err_file) -> tuple[bytes, bytes]:
        """Rewind and read both capture files."""
        out_file.seek(0)
        err_file.seek(0)
        return out_file.read(), err_file.read()

    @staticmethod
    def _raise_if_output_overflow(options, out_bytes, err_bytes) -> None:
        # Octave catches SIGXFSZ and truncates, so overflow shows up
        # as a capture file that reached the RLIMIT_FSIZE ceiling.
        if len(out_bytes) >= FILE_SIZE_LIMIT or len(err_bytes) >= FILE_SIZE_LIMIT:
            raise OctaveRuntimeError(
                f"Your `{options.obj_name}` produced too much output "
                f"(limit: {FILE_SIZE_LIMIT} bytes)."
            )

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
