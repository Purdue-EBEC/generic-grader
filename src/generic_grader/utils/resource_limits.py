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
