"""Classify whether an exception is a grader-internal fault.

A security exception raised from *library* code (for example matplotlib
removing its font-cache lock file via ``os.unlink``) is a bug in the
autograder, not a student error.  Reporting it as a student error sends the
student chasing a course hint for something they did not do.

The classifier walks the exception traceback from the innermost frame
outward, skipping grader machinery, stdlib and pseudo-file frames (stdlib
modules such as ``pathlib`` and ``contextlib`` are transparent wrappers, as
are dynamically compiled ``<string>`` / ``<frozen ...>`` frames), and
inspects the first remaining frame.  If that frame lives in a third-party
install directory the fault is attributed to the grader.

Known limitations
-----------------
Attribution uses the traceback only, so it only decides which *message* a
student sees; the blocked call is always blocked either way.

* A student can pass a blocked callable to library code (for example
  ``np.vectorize(os.remove)``) and be attributed to the grader.  Requiring
  that no student frame sit above the library frame is not an option: the
  motivating case, a student module importing matplotlib, always has one.
* Frame filenames are not authenticated: ``compile(src, <library path>,
  "exec")`` classifies as library code.
* Do not reuse this classifier as an allow-list that lets blocked calls
  succeed (#197) without an additional check, because of the
  two points above.
* Chained exceptions (``__cause__`` / ``__context__``) are not inspected, so
  a library that re-raises a different exception is treated as a student
  error.
* Editable installs outside site-packages are not recognized as libraries,
  and paths are compared case-sensitively.

See issue #198.
"""

import logging
import os
import re
import site
import sysconfig
import traceback

import generic_grader
from generic_grader.utils.exceptions import (
    DisallowedFileAccessError,
    DisallowedFunctionCallError,
    DisallowedImportError,
)

_logger = logging.getLogger(__name__)
# Without a handler, Python's last-resort handler prints the record and its
# traceback to stderr, which Gradescope shows to students.
_logger.addHandler(logging.NullHandler())

# Limit errors (timeout, exit, input, log size) are student outcomes even when
# they fire inside library code, so only security blocks can be grader faults.
# Library-origin DisallowedImportError is effectively unreachable: libraries
# are trusted importers (see patches._caller_is_trusted).
_SECURITY_ERRORS = (
    DisallowedFileAccessError,
    DisallowedFunctionCallError,
    DisallowedImportError,
)


def _compute_library_dirs():
    """Return third-party install directories (site-packages, dist-packages)."""
    paths = {
        sysconfig.get_paths()["purelib"],
        sysconfig.get_paths()["platlib"],
        site.getusersitepackages(),
        *getattr(site, "getsitepackages", list)(),
    }
    return tuple(sorted(os.path.realpath(p) for p in paths if p))


def _compute_stdlib_dirs():
    """Return the standard-library directories."""
    paths = {
        sysconfig.get_paths()["stdlib"],
        sysconfig.get_paths()["platstdlib"],
        os.path.dirname(os.__file__),
    }
    return tuple(sorted(os.path.realpath(p) for p in paths if p))


# Third-party install directories.  Kept distinct from the stdlib so that a
# stdlib wrapper (e.g. pathlib) is treated as transparent rather than as the
# origin of the call.  Snapshot at import time; later sys.path changes are ignored.
_LIBRARY_DIRS = _compute_library_dirs()

# Standard-library directories, treated as transparent wrappers.
_STDLIB_DIRS = _compute_stdlib_dirs()

# The grader's own package directory; its frames are never the origin of a call.
_GRADER_DIR = os.path.realpath(os.path.dirname(generic_grader.__file__))


def _is_pseudo_file(filename):
    """Return True for ``<string>`` / ``<frozen os>`` style filenames."""
    return filename.startswith("<") and filename.endswith(">")


def _is_inside(path, directory):
    """Return True if `path` is inside `directory`."""
    try:
        return os.path.commonpath([path, directory]) == directory
    except ValueError:
        # Different drives on Windows etc.
        return False


def _library_origin(e):
    """Return the library file that triggered security error `e`, else None."""
    if not isinstance(e, _SECURITY_ERRORS):
        return None

    for frame, _ in reversed(list(traceback.walk_tb(e.__traceback__))):
        filename = frame.f_code.co_filename
        if _is_pseudo_file(filename):
            continue
        try:
            real = os.path.realpath(filename)
        except (OSError, ValueError):
            return None
        # Grader machinery is transparent even when installed in site-packages,
        # so a blocked call made by grader code itself is blamed on the caller.
        if _is_inside(real, _GRADER_DIR):
            continue
        # Library frames are checked before stdlib: in a virtualenv,
        # site-packages is nested inside platstdlib.
        if any(_is_inside(real, d) for d in _LIBRARY_DIRS):
            return filename
        if any(_is_inside(real, d) for d in _STDLIB_DIRS):
            continue
        return None

    return None


def is_grader_internal_fault(e: BaseException) -> bool:
    """Return True if `e` is a grader fault rather than a student error.

    Only the grader's own security blocks (``Disallowed*Error``) can be grader
    faults; limit errors and a library's own exceptions caused by student
    misuse are not.  The origin of the call is the innermost frame that is
    neither grader machinery, stdlib, nor a pseudo-file (``<string>`` /
    ``<frozen ...>``).  If that frame lives in a third-party install
    directory, the fault is the grader's.
    """
    return _library_origin(e) is not None


def report_grader_fault(e: BaseException) -> str | None:
    """Log a grader fault and return a short, path-free description of it.

    Return None, logging nothing, if `e` is not a grader fault.

    The student message omits paths and the traceback, so the log record is
    the only place they appear.  It goes to this module's logger, which has a
    ``NullHandler``: nothing reaches stderr (and so the student) unless the
    harness configures a handler for ``generic_grader``.  The record also
    lets a student-triggered case (see the known limitations) be recognized.
    """
    origin = _library_origin(e)
    if origin is None:
        return None

    _logger.error(
        "Grader fault attributed to library code %s: %r. If the student passed "
        "a blocked callable or a protected path to a library, this may be a "
        "student violation rather than a grader bug.",
        origin,
        e,
        exc_info=e,
    )

    # The filename is untrusted (see the known limitations); keep it from
    # breaking the Markdown code span or injecting line breaks.
    basename = re.sub(r"[^\w.+-]", "_", os.path.basename(origin))
    return f"`{type(e).__name__}` raised in `{basename}`"
