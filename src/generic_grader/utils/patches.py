from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from freezegun import freeze_time

from generic_grader.utils.exceptions import (
    ExitError,
    QuitError,
    TurtleDoneError,
    TurtleWriteError,
)
from generic_grader.utils.mocks import (
    make_mock_function_noop,
    make_mock_function_raise_error,
)
from generic_grader.utils.options import Options
from generic_grader.utils.resource_limits import memory_limit, time_limit


def make_turtle_done_patches(modules):
    """
    Patch extra calls to done()/mainloop().

    This prevents hangs when the student mistakenly calls one of them.  The `modules`
    parameter should be a list or tuple of the assignment's module names.  E.g.
    `modules = ["vowels", "random_vowels"]`.
    """
    return [
        {
            "args": make_mock_function_raise_error(f"{module}.{func}", TurtleDoneError),
            "kwargs": {"create": True},
        }
        for func in ["done", "mainloop"]
        for module in ["turtle", *modules]
    ]


def make_turtle_write_patches(modules):
    """
    Make patches to block access to `turtle.write`.

    The `modules` parameter should be a list or tuple of the assignment's module names.
    E.g. `modules = ["vowels", "random_vowels"]`.
    """
    return [
        {
            "args": make_mock_function_raise_error(f"{module}.write", TurtleWriteError),
            "kwargs": {"create": True},
        }
        for module in ["turtle", *modules]
    ]


def make_pyplot_noop_patches(modules):
    """Patch `matplotlib.pyplt.show` with a noop."""
    return [
        {
            "args": make_mock_function_noop(f"{module}.{func}"),
            "kwargs": {"create": True},
        }
        for func in ["savefig", "show"]
        for module in ["matplotlib.pyplot", *modules]
    ]


def make_exit_quit_patches():
    """Patch the builtins exit and quit functions."""
    return [
        {
            "args": make_mock_function_raise_error("builtins.exit", ExitError),
        },
        {"args": make_mock_function_raise_error("builtins.quit", QuitError)},
    ]


@contextmanager
def custom_stack(o: Options):
    """Create a custom stack with resource limits and patches."""
    with ExitStack() as stack:
        # Add custom resource limits
        stack.enter_context(time_limit(o.time_limit))
        stack.enter_context(memory_limit(o.memory_limit_GB))
        if o.fixed_time:
            stack.enter_context(freeze_time(o.fixed_time))
        patches = (o.patches or []) + make_exit_quit_patches()
        for p in patches:
            stack.enter_context(
                patch(
                    *p.get("args", ()),  # permit missing args
                    **p.get("kwargs", {}),  # permit missing kwargs
                )
            )

        yield
