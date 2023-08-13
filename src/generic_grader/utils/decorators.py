from functools import wraps

from generic_grader.utils.options import Options


def weighted(func):
    """Decorator that marks a test method as having a parameterized weight.

    The weight attribute of the test method is set when the decorated method is
    called as opposed to when it is defined.  This allows parameterized test
    methods to have their weight set by their parameters.

    The decorator expects to find an Options object in the arguments. If it is
    not found, the weight is taken from the default instance of Options.

    ```
    @weighted
    def f(*args, **kwargs):
        ...
    ```

    """

    def set_weight(*args, **kwargs):
        """Add a weight attribute to the wrapping function."""
        for arg in args:
            if isinstance(arg, Options):
                wrapper.__weight__ = arg.weight
                return

        for key, value in kwargs.items():
            if isinstance(value, Options):
                wrapper.__weight__ = value.weight
                return

        weight = kwargs.get("options", Options()).weight
        wrapper.__weight__ = weight

    def set_score(score):
        """Set the score of the test."""
        wrapper.__score__ = score

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        set_weight(*args, **kwargs)
        # Inject a set_score method into the test function's instance.
        self.set_score = set_score
        return func(self, *args, **kwargs)

    return wrapper
