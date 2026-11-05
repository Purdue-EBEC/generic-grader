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
    temporary directory (see :meth:`OctaveRuntime._stage_function_run`)
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

  What is **not** enforced: there is no filesystem, network or process
  isolation.  Student ``.m`` code can run shell commands with
  ``system()`` and read any file the grader user can read, including
  the reference solution and test files.  Run the grader as an
  unprivileged user in a throwaway container.

* **stdin (simulated user input).**  Anything in ``options.entries`` is
  joined with newlines and fed to the child process's stdin.  In
  Octave, ``input("prompt")`` reads from ``stdin`` when running in
  non-interactive mode with ``--eval``, which is exactly the mode we
  invoke.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from textwrap import dedent
from unittest import TestCase

from generic_grader.runtimes.base import (
    RuntimeExecutionError,
    RuntimeResult,
    RuntimeTimeoutError,
    RuntimeUnavailableError,
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

        # Script mode runs in the file's own directory, which puts it on
        # Octave's load path.  Function mode runs from a private copy.
        script_dir = os.path.dirname(handle)
        stem = os.path.splitext(os.path.basename(handle))[0]
        stage_dir = None
        source_path = None
        try:
            if options.args or options.kwargs:
                stage_dir, source_path = self._stage_function_run(options, handle)
                script_dir = stage_dir
            return self._launch(
                options, executable, script_dir, stem, source_path, log, entries
            )
        finally:
            if stage_dir is not None:
                shutil.rmtree(stage_dir, ignore_errors=True)

    @staticmethod
    def _stage_function_run(options: Options, handle: str) -> tuple[str, str | None]:
        """Copy ``handle`` into a fresh directory for a function-mode call.

        Octave resolves ``foo(...)`` by file name, so the reference
        (``ref_foo.m``) and student (``foo.m``) files would shadow each
        other if run side by side.  The directory holds the other ``.m``
        files from the submission directory, except the two sides' own
        files, so helper functions are still found.

        Returns ``(stage_dir, source_path)``.  ``source_path`` is ``None``
        when ``obj_name`` is the file's primary function: the file is
        staged as ``<obj_name>.m`` and called directly.  Otherwise it is
        the staged copy to ``source`` as a script, which is the only way
        to call a subfunction from outside its file.
        """
        src_dir = os.path.dirname(handle)
        handle_stem = os.path.splitext(os.path.basename(handle))[0]
        sub_stem = os.path.basename(options.sub_module)
        sides = {handle_stem, sub_stem, os.path.basename(options.ref_module)}

        stage_dir = tempfile.mkdtemp(prefix="gg_octave_run_")
        try:
            for name in os.listdir(src_dir):
                path = os.path.join(src_dir, name)
                if (
                    name.endswith(".m")
                    and name[:-2] not in sides
                    and os.path.isfile(path)
                ):
                    shutil.copy2(path, stage_dir)
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

    def _launch(
        self,
        options: Options,
        executable: str,
        script_dir: str,
        stem: str,
        source_path: str | None,
        log,
        entries,
    ) -> RuntimeResult:
        """Run Octave in ``script_dir`` and translate its outcome."""
        eval_expr = self._build_eval_expression(options, stem, source_path)
        mem_bytes = max(1, int(options.memory_limit_GB * _GB))
        cpu_seconds = max(1, int(options.time_limit) + 1)
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
        env = self._safe_env()

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
                )
            except FileNotFoundError as e:
                # Race: which() found the executable a moment ago but it
                # vanished before exec.  Convert to the same
                # not-installed error the up-front check produces.
                raise OctaveNotInstalledError(str(e)) from e

            try:
                proc.communicate(input=stdin_bytes, timeout=options.time_limit)
            except subprocess.TimeoutExpired:
                self._reap_group(proc)
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
                self._reap_group(proc)
                raise

            self._reap_group(proc)
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

            return RuntimeResult(returned_values=None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_eval_expression(
        options: Options, stem: str, source_path: str | None = None
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
          the file is defined (see :meth:`_stage_function_run`).

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
            body = f"{options.obj_name}{_format_args(options.args, options.kwargs)};"
            if source_path:
                escaped = source_path.replace("'", "''")
                body = f"source('{escaped}'); {body}"
        return dedent(
            f"""\
            try
              {body}
            catch err
              fprintf(stderr, '%s\\n', err.message);
              exit(1);
            end_try_catch
            exit(0);
            """
        )

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
        return env

    @staticmethod
    def _reap_group(proc) -> None:
        """SIGKILL the child's process group and reap the child.

        Called on every exit path (normal, nonzero, timeout,
        exception) so grandchildren backgrounded via ``system()``
        cannot outlive the run.
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
