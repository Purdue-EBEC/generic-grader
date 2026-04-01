import os
import resource
import signal
import sys
from contextlib import contextmanager

from generic_grader.utils.exceptions import UserTimeoutError


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


def _get_current_vm_bytes():
    """Return the current virtual memory size of this process in bytes.

    Reads VmSize from /proc/self/status, which represents the total
    virtual address space used by the process.
    """
    with open(f"/proc/{os.getpid()}/status") as f:
        for line in f:
            if line.startswith("VmSize:"):
                return int(line.split()[1]) * 1024  # kB to bytes
    return 0  # pragma: no cover


@contextmanager
def memory_limit(max_gibibytes):
    """A context manager to limit memory usage while running submitted code.

    Sets RLIMIT_AS relative to the current virtual memory usage so that
    the enclosed code gets exactly max_gibibytes of additional address
    space, regardless of how much memory the Python runtime and its
    libraries already consume.
    """
    GiB = 2**30
    max_bytes = int(max_gibibytes * GiB)
    current_vm = _get_current_vm_bytes()

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (current_vm + max_bytes, hard))
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
