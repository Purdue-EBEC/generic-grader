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

        for value in kwargs.values():
            if isinstance(value, Options):
                return value.weight

        return Options().weight

    def set_score(self, score):
        """Set the score of the test."""
        getattr(type(self), self._testMethodName).__score__ = score

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        """Add mechanism to track gradescope variables.
        The weight is set immediately, and a `set_score` method is added to the
        testcase instance to allow partial credit to be set by the test itself.
        """

        test_method = getattr(type(self), self._testMethodName)
        test_method.__weight__ = get_weight(*args, **kwargs)

        # Inject a set_score method into the test case instance.
        self.set_score = set_score

        # Set the score to 0 by default.
        self.set_score(self, 0)

        func(self, *args, **kwargs)

    return wrapper
