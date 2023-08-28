import unittest
from functools import wraps

from generic_grader.utils.options import Options


def weighted(func):
    """Decorator that marks a test method as having a parameterized weight.

    The weight attribute of the test method is set when the decorated method is
    called as opposed to when it is defined.  This allows parameterized test
    methods to have their weight set by their parameters.

    The decorator expects to find an Options object in the arguments. If it is
    not found, the weight is taken from the default instance of Options.

    Any weighted test method also has a set_score method injected into it to
    enable partial credit.

    ```
    @weighted
    def f(*args, **kwargs):
        ...
    ```

    """

    def get_weight(*args, **kwargs):
        """Search for the Options argument and return its weight."""

        for arg in args:
            if isinstance(arg, Options):
                return arg.weight

        for key, value in kwargs.items():
            if isinstance(value, Options):
                return value.weight

        return Options().weight

    def set_score(self, score):
        """Set the score of the test."""

        type(self).__gradescope__["scores"][-1] = score

    def set_gradescope_vars(cls):
        """Set the gradescope variables as attributes on each test."""

        test_case_names = unittest.TestLoader().getTestCaseNames(cls)
        for test_case_name in test_case_names:
            test_case = getattr(cls, test_case_name)
            test_case.__weight__ = cls.__gradescope__["weights"].pop(0)
            test_case.__score__ = cls.__gradescope__["scores"].pop(0)

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        """Add mechanism to track gradescope variables.

        A __gradescope__ dict is added to the class to store each test's
        variables.  The weight is set immediately, and a `set_score` method is
        added to the function to allow partial credit to be set by the test
        itself.  Once all the tests are complete, the cleanup function migrates
        the gradescope variables to the test methods as Gradescope expects.
        """

        cls = type(self)
        if not hasattr(cls, "__gradescope__"):
            cls.__gradescope__ = {"weights": [], "scores": []}

        cls.__gradescope__["weights"].append(get_weight(*args, **kwargs))
        cls.__gradescope__["scores"].append(None)

        # Inject a set_score method into the test function's instance.
        self.set_score = set_score

        # Add a function to process the gradescope variables exactly once.  This
        # will run after all the test methods have been called.
        cleanup_functions = [f for f, args, kwargs in cls._class_cleanups]
        if set_gradescope_vars not in cleanup_functions:
            cls.addClassCleanup(set_gradescope_vars, cls)

        return func(self, *args, **kwargs)

    return wrapper
