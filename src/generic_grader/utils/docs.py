"""Functions to generate customized docstrings for parameterized tests."""

import textwrap


def make_call_str(func_name="main", args=[], kwargs={}):
    """Construct and return a function call string from its name, and
    arguments.
    """
    # Create a list of position argument strings.
    args_lst = list(map(repr, args))

    # Add keyword argument strings.
    args_lst.extend(f"{k}={repr(v)}" for k, v in kwargs.items())

    # Construct the function call with a comma separated list of arguments.
    call_str = f'{func_name}({", ".join(args_lst)})'

    return call_str


def ordinalize(n):
    """Return the ordinal number representation of n."""

    # Set the most common suffix
    suffix = "th"

    # Handle special cases:
    # i.e. numbers ending in 1, 2 or 3 but not ending in 11, 12, or 13
    ones, tens = abs(n) % 10, abs(n) % 100
    if ones in (1, 2, 3) and tens not in (11, 12, 13):
        suffix = ("st", "nd", "rd")[ones - 1]

    return f"{n}{suffix}"


def make_line_range(start, n_lines):
    """Return the range of lines being checked expressed in words."""
    if n_lines == 1:
        return f"line {start}"
    else:
        stop = start + n_lines - 1 if n_lines else "the end"
        return f"lines {start} through {stop}"


def oxford_list(sequence):
    """Return the strings in sequence formatted as an Oxford list."""
    if len(sequence) <= 2:
        # Handle sequences of 0, 1, or 2 items.
        return " and ".join(sequence)
    else:
        # Handle sequences of 3 or more items.
        last = sequence[-1]
        not_last = ", ".join(sequence[:-1])
        return f"{not_last}, and {last}"


def get_wrapper() -> textwrap.TextWrapper:
    """Return an instance of the text wrapper used across tests."""
    return textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")
