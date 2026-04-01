import time

import pytest

from generic_grader.utils.exceptions import UserTimeoutError
from generic_grader.utils.resource_limits import (
    _get_current_vm_bytes,
    memory_limit,
    time_limit,
)

time_limit_cases = [
    {"length": 0.5, "result": None},
    {"length": 1, "result": UserTimeoutError},
    {"length": 2, "result": UserTimeoutError},
]


@pytest.mark.parametrize("case", time_limit_cases)
def test_time_limit(case):
    """Test the time_limit function."""
    if case["result"] is not None:
        with pytest.raises(case["result"]):
            with time_limit(1):
                time.sleep(case["length"])
    else:  #  The ideal case where no exception is raised
        with time_limit(1):
            time.sleep(case["length"])


def test_get_current_vm_bytes():
    """Test that _get_current_vm_bytes returns a positive integer."""
    vm_bytes = _get_current_vm_bytes()
    assert isinstance(vm_bytes, int)
    assert vm_bytes > 0


memory_limit_cases = [
    {"usage": 0.5, "result": None},
    {"usage": 1.5, "result": MemoryError},
    {"usage": 2, "result": MemoryError},
]


@pytest.mark.parametrize("case", memory_limit_cases)
def test_memory_limit(case):
    """Test the memory_limit function.

    The limit is relative to current VM usage, so allocating
    usage * GiB within a 1 GiB limit should succeed only when
    usage is well below the limit.
    """
    if case["result"] is not None:
        with pytest.raises(case["result"]):
            with memory_limit(1):
                " " * int(case["usage"] * 2**30)
    else:
        with memory_limit(1):
            " " * int(case["usage"] * 2**30)


def test_memory_limit_message():
    """Test that the MemoryError includes a descriptive message."""
    with pytest.raises(MemoryError, match="maximum allowed memory"):
        with memory_limit(1):
            " " * int(2 * 2**30)


def test_memory_limit_restores_on_success():
    """Test that RLIMIT_AS is restored after a successful block."""
    import resource

    soft_before, hard_before = resource.getrlimit(resource.RLIMIT_AS)
    with memory_limit(1):
        pass
    soft_after, hard_after = resource.getrlimit(resource.RLIMIT_AS)
    assert soft_before == soft_after
    assert hard_before == hard_after


def test_memory_limit_restores_on_error():
    """Test that RLIMIT_AS is restored after a MemoryError."""
    import resource

    soft_before, hard_before = resource.getrlimit(resource.RLIMIT_AS)
    with pytest.raises(MemoryError):
        with memory_limit(1):
            " " * int(2 * 2**30)
    soft_after, hard_after = resource.getrlimit(resource.RLIMIT_AS)
    assert soft_before == soft_after
    assert hard_before == hard_after
