import datetime
from collections.abc import Callable

from attrs import Factory, define


@define(kw_only=True, frozen=True)
class Options:
    # Base
    weight: int = 0
    init: Callable[[], None] | None = None
    ref_module: str = "tests/reference"
    sub_module: str = Factory(str)
    required_files: tuple = Factory(tuple)
    ignored_files: tuple = Factory(tuple)
    hint: str = Factory(str)
    patches: list[dict[str, list[str, Callable]]] = Factory(list)

    # Input
    entries: list[str] = Factory(list)

    # Output
    interaction: int = 0
    start: int = 1
    n_lines: int | None = None
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
    args: list = Factory(list)
    kwargs: dict = Factory(dict)
    expected_set: set = Factory(set)
    expected_perms: set = Factory(set)
    validator: Callable | None = None

    # File
    filenames: tuple = Factory(tuple)

    # Code
    expected_minimum_depth: int = 1

    # Plots
    prop: str = ""
    prop_kwargs: dict = Factory(dict)

    # Stats
    expected_distribution: dict = {0: 0}
    relative_tolerance: float = 1e-7
    absolute_tolerance: int = 0

    def __attrs_post_init__(self):
        for attr in self.__annotations__:
            if attr == "init":
                if not isinstance(getattr(self, attr), (Callable, type(None))):
                    raise ValueError(
                        f"`{attr}` must be of type <class 'function'> or {type(None)}. Got {type(getattr(self, attr))} instead."
                    )
            elif attr in ["patches", "entries"]:
                if not isinstance(getattr(self, attr), list):
                    raise ValueError(
                        f"`{attr}` must be of type list. Got {type(getattr(self, attr))} instead."
                    )
            elif not isinstance(getattr(self, attr), self.__annotations__[attr]):
                raise ValueError(
                    f"`{attr}` must be of type {self.__annotations__[attr]}. Got {type(getattr(self, attr))} instead."
                )


@define(kw_only=True, frozen=True)
class ImageOptions:
    init: Callable[[], None] | None = None
    ref_module: str = "tests.reference"
    sub_module: str = ""
    obj_name: str = "main"
    args: list = Factory(list)
    kwargs: dict = Factory(dict)
    entries: tuple = Factory(tuple)
    A: str = ""
    B: str = ""
    region_a: str = ""
    region_b: str = ""
    mode: str = "exactly"
    threshold: int = 0
    delta: int = 0
    hint: str = ""
    patches: str = ""

    def __attrs_post_init__(self):
        for attr in self.__annotations__:
            if attr == "init":
                if not isinstance(getattr(self, attr), (Callable, type(None))):
                    raise ValueError(
                        f"`{attr}` must be of type <class 'function'> or {type(None)}. Got {type(getattr(self, attr))} instead."
                    )
            elif not isinstance(getattr(self, attr), self.__annotations__[attr]):
                raise ValueError(
                    f"`{attr}` must be of type {self.__annotations__[attr]}. Got {type(getattr(self, attr))} instead."
                )
