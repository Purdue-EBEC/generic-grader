"""Unprivileged identity for running untrusted student code.

A grader that runs as root (as Gradescope's does) can launch the student's
program as a different, unprivileged user.  Combined with a reference and
test files that user cannot read, student code can no longer read them.

Configuration is through the environment:

* ``GENERIC_GRADER_SANDBOX_USER`` -- name or numeric uid of the user to run
  student code as.  Unset: use ``nobody`` when the grader is root, do nothing
  otherwise.  ``none``: never drop privileges.  A user other than ``nobody``
  is assumed to be dedicated to the grader, which enables
  :func:`kill_all_processes`.
* ``GENERIC_GRADER_SUBMISSION_DIR`` -- directory holding only what the student
  submitted (``/autograder/submission`` on Gradescope).
"""

from __future__ import annotations

import os
import pwd
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from generic_grader.runtimes.base import RuntimeUnavailableError

SANDBOX_USER_ENV = "GENERIC_GRADER_SANDBOX_USER"
SUBMISSION_DIR_ENV = "GENERIC_GRADER_SUBMISSION_DIR"
DEFAULT_USER = "nobody"

# Run as the sandbox user.  kill(-1) signals every process that user owns, so
# refuse unless the uid really changed: as root it would signal everything.
_KILL_ALL = """import os, signal, sys
uid = int(sys.argv[1])
if uid == 0 or os.getresuid() != (uid, uid, uid):
    sys.exit(2)
os.kill(-1, signal.SIGKILL)
"""


@dataclass(frozen=True)
class Sandbox:
    """The unprivileged identity student code runs as."""

    uid: int
    gid: int
    # True when the user was chosen explicitly, i.e. it is not the shared
    # ``nobody`` account, so every process it owns belongs to the grader.
    dedicated: bool


def resolve_sandbox() -> Sandbox | None:
    """Return the identity to run student code as, or ``None`` for no drop."""
    setting = os.environ.get(SANDBOX_USER_ENV, "").strip()
    if setting.lower() == "none":
        return None
    if os.geteuid() != 0:
        if not setting:
            return None
        raise RuntimeUnavailableError(
            f"{SANDBOX_USER_ENV}={setting!r} needs the grader to run as root "
            "so it can switch users."
        )

    try:
        entry = (
            pwd.getpwuid(int(setting))
            if setting.isdigit()
            else pwd.getpwnam(setting or DEFAULT_USER)
        )
    except KeyError:
        raise RuntimeUnavailableError(
            f"The sandbox user {setting or DEFAULT_USER!r} does not exist on "
            f"this host. Create it, or set {SANDBOX_USER_ENV}."
        ) from None
    if entry.pw_uid == 0 or entry.pw_gid == 0:
        raise RuntimeUnavailableError("The sandbox user must not be root.")
    return Sandbox(
        uid=entry.pw_uid,
        gid=entry.pw_gid,
        dedicated=bool(setting) and entry.pw_name != DEFAULT_USER,
    )


def submission_dir() -> str:
    """Return the directory that holds only the student's submitted files."""
    path = os.environ.get(SUBMISSION_DIR_ENV, "")
    if not path:
        raise RuntimeUnavailableError(
            f"{SUBMISSION_DIR_ENV} is not set. It must name a directory that "
            "contains only the student's files (/autograder/submission on "
            "Gradescope), so no grader file is exposed to student code."
        )
    return path


def can_read(sandbox: Sandbox, path: str) -> bool:
    """Whether ``sandbox`` can open ``path`` for reading (mode bits only).

    ACLs and capabilities are not considered.  Supplementary groups are
    ignored because student code runs with none.
    """
    real = Path(os.path.realpath(path))

    def allows(target: Path, bit: int) -> bool:
        st = target.stat()
        if st.st_uid == sandbox.uid:
            shift = 6
        elif st.st_gid == sandbox.gid:
            shift = 3
        else:
            shift = 0
        return bool(st.st_mode >> shift & bit)

    return all(allows(parent, 0o1) for parent in real.parents) and allows(real, 0o4)


def kill_all_processes(sandbox: Sandbox) -> None:
    """SIGKILL every process owned by the sandbox user.

    Catches children that left the process group (``setsid``) and so escape
    ``killpg``.  Only valid for a dedicated user.
    """
    if not sandbox.dedicated:
        raise ValueError("Refusing to kill every process of a shared user.")
    subprocess.run(
        [sys.executable, "-I", "-c", _KILL_ALL, str(sandbox.uid)],
        user=sandbox.uid,
        group=sandbox.gid,
        extra_groups=[],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )


__all__ = (
    "DEFAULT_USER",
    "SANDBOX_USER_ENV",
    "SUBMISSION_DIR_ENV",
    "Sandbox",
    "can_read",
    "kill_all_processes",
    "resolve_sandbox",
    "submission_dir",
)
