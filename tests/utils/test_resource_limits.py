import time

import pytest

from generic_grader.utils.exceptions import UserTimeoutError
from generic_grader.utils.resource_limits import memory_limit, time_limit

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


memory_limit_cases = [
    {"usage": 0.5, "result": None},
    {"usage": 1, "result": MemoryError},
    {"usage": 2, "result": MemoryError},
]


@pytest.mark.parametrize("case", memory_limit_cases)
@pytest.mark.skip(reason="Memory limit is not working on some systems (see #65).")
def test_memory_limit(case):
    """Test the memory_limit function."""
    if case["result"] is not None:
        with pytest.raises(case["result"]):
            with memory_limit(1):
                " " * int(case["usage"] * 2**30)
    else:
        with memory_limit(1):
            " " * int(case["usage"] * 2**30)
