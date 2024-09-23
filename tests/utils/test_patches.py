import pytest

from generic_grader.utils.options import Options
from generic_grader.utils.patches import (
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


def test_make_turtle_done_patches_format():
    """Make sure the patches are properly formatted and load into Options properly."""
    result = make_turtle_done_patches(["sub_module"])

    assert Options(patches=result)
