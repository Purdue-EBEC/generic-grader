import datetime
from collections.abc import Callable
from typing import NamedTuple


class Options(NamedTuple):
    # Base
    weight: int = 0
    init: Callable[[], None] | None = None
    ref_module: str = "tests/reference"
    sub_module: str = ""
    required_files: tuple = ()
    ignored_files: tuple = ()
    hint: str = ""
    patches: list[dict[str, list[str, Callable]]] = []

    # Input
    entries: tuple = ()

    # Output
    interaction: int = 0
    start: int = 1
    n_lines: int = None
    line_n: int = 1
    value_n: int = 1
    ratio: int = 1  # exact match
    log_limit: int = 0
    fixed_time: bool | datetime.datetime | str = False
    debug: bool = False
    time_limit: int = 1
    memory_limit_GB: float = 1.4

    # Callable
    obj_name: str = "main"
    args: list = []
    kwargs: dict = {}
    expected_set: set = set()
    expected_perms: set = set()
    validator: Callable | None = None

    # File
    filenames: tuple = ()

    # Code
    expected_minimum_depth: int = 1

    # Plots
    prop: str = ""
    prop_kwargs: dict = {}

    # Stats
    expected_distribution: dict = {0: 0}
    relative_tolerance: float = 1e-7
    absolute_tolerance: int = 0


class ImageOptions(NamedTuple):
    init: Callable[[], None] = None
    ref_module: str = "tests.reference"
    sub_module: str = ""
    obj_name: str = "main"
    args: list = []
    kwargs: dict = {}
    entries: tuple = ()
    A: str = ""
    B: str = ""
    region_a: str = ""
    region_b: str = ""
    mode: str = "exactly"
    threshold: int = 0
    delta: int = 0
    hint: str = ""
    patches: str = ""
