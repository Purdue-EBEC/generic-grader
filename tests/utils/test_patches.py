import datetime
import time

import pytest

from generic_grader.utils.exceptions import ExitError, QuitError, UserTimeoutError
from generic_grader.utils.mocks import make_mock_function_raise_error
from generic_grader.utils.options import Options
from generic_grader.utils.patches import (
    custom_stack,
    make_exit_quit_patches,
    make_pyplot_noop_patches,
    make_turtle_done_patches,
    make_turtle_write_patches,
)


def test_make_pyplot_noop_patches_names():
    result = make_pyplot_noop_patches(["sub_module"])

    mpl_func_name_0, _ = result[0]["args"]
    sub_func_name_0, _ = result[1]["args"]
    mpl_func_name_1, _ = result[2]["args"]
    sub_func_name_1, _ = result[3]["args"]

    assert mpl_func_name_0 == "matplotlib.pyplot.savefig"
    assert mpl_func_name_1 == "matplotlib.pyplot.show"
    assert sub_func_name_0 == "sub_module.savefig"
    assert sub_func_name_1 == "sub_module.show"

    with pytest.raises(IndexError):
        result[4]


def test_pyplot_create():
    """Make sure create is set to True."""
    for patch in make_pyplot_noop_patches(["sub_module"]):
        assert patch["kwargs"]["create"] is True


def test_make_pyplot_noop_patches_format():
    """Make sure the patches are properly formatted and load into Options properly."""
    result = make_pyplot_noop_patches(["sub_module"])

    assert Options(patches=result)


def test_make_turtle_write_patches_names():
    result = make_turtle_write_patches(["sub_module"])

    t_func_name, _ = result[0]["args"]

    s_func_name, _ = result[1]["args"]

    assert t_func_name == "turtle.write"
    assert s_func_name == "sub_module.write"

    with pytest.raises(IndexError):
        result[2]


def test_turtle_write_create():
    """Make sure create is set to True."""
    for patch in make_turtle_write_patches(["sub_module"]):
        assert patch["kwargs"]["create"] is True


def test_make_turtle_write_patches_format():
    """Make sure the patches are properly formatted and load into Options properly."""
    result = make_turtle_write_patches(["sub_module"])

    assert Options(patches=result)


def test_make_turtle_done_patches_names():
    result = make_turtle_done_patches(["sub_module"])

    t_func_name_0, _ = result[0]["args"]

    s_func_name_0, _ = result[1]["args"]

    t_func_name_1, _ = result[2]["args"]

    s_func_name_1, _ = result[3]["args"]
    assert t_func_name_0 == "turtle.done"
    assert t_func_name_1 == "turtle.mainloop"
    assert s_func_name_0 == "sub_module.done"
    assert s_func_name_1 == "sub_module.mainloop"

    with pytest.raises(IndexError):
        result[4]


def test_turtle_done_create():
    """Make sure create is set to True."""
    for patch in make_turtle_done_patches(["sub_module"]):
        assert patch["kwargs"]["create"] is True


def test_make_turtle_done_patches_format():
    """Make sure the patches are properly formatted and load into Options properly."""
    result = make_turtle_done_patches(["sub_module"])

    assert Options(patches=result)


def test_make_exit_quit_patches_names():
    """Test that the exit and quit functions are properly patched."""
    result = make_exit_quit_patches()

    exit_func_name, _ = result[0]["args"]

    quit_func_name, _ = result[1]["args"]

    assert exit_func_name == "builtins.exit"
    assert quit_func_name == "builtins.quit"

    with pytest.raises(IndexError):
        result[2]


def test_make_exit_quit_patches_format():
    """Make sure the patches are properly formatted and load into Options properly."""
    result = make_exit_quit_patches()

    assert Options(patches=result)


def test_stack_time():
    """Test that the custom stack properly freezes time."""
    o = Options(fixed_time=datetime.datetime(2000, 1, 1, 1))
    with custom_stack(o):
        assert datetime.datetime.now() == datetime.datetime(2000, 1, 1, 1)


def test_stack_exit():
    """Test that the custom stack properly patches exit and quit."""
    o = Options(patches=make_exit_quit_patches())
    with custom_stack(o):
        with pytest.raises(ExitError):
            exit()
        with pytest.raises(QuitError):
            quit()


def test_stack_timelimit():
    """Test that the custom stack properly patches time limit."""
    o = Options(time_limit=1)
    with custom_stack(o):
        with pytest.raises(UserTimeoutError):
            while True:
                time.sleep(1)


@pytest.mark.skip(reason="Memory limit is not working on some systems (see #65).")
def test_stack_memorylimit():
    """Test that the custom stack properly patches memory limit."""
    o = Options()
    with custom_stack(o):
        with pytest.raises(MemoryError):
            [1] * 100000000000


def test_stack_extra_patches():
    """Test that the custom stack properly patches extra patches."""
    o = Options(
        patches=[{"args": make_mock_function_raise_error("builtins.print", ValueError)}]
    )
    with custom_stack(o):
        with pytest.raises(ValueError):
            print("Hello, world!")
