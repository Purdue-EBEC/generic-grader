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
        type(self).__gradescope__[self._testMethodName]["score"] = score

    def set_gradescope_vars(self):
        """Set the Gradescope variables as attributes on this test method."""

        # Get a reference to the test method.
        cls = type(self)
        test_method_name = self._testMethodName
        test_method = getattr(cls, test_method_name)

        # Add the Gradescope variables as attributes.
        test_method_vars = cls.__gradescope__[test_method_name]
        test_method.__weight__ = test_method_vars["weight"]
        test_method.__score__ = test_method_vars["score"]

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        """Add mechanism to track gradescope variables.

        A __gradescope__ dict is added to the class to store each test's
        variables.  The weight is set immediately, and a `set_score` method is
        added to the function to allow partial credit to be set by the test
        itself.  Once a test case has run, the cleanup function migrates the
        gradescope variables to that test case instance's test method as
        Gradescope expects."""

        cls = type(self)
        if not hasattr(cls, "__gradescope__"):
            # This could have been attached to the test case instance, but after
            # being wrapped by parameterize, all instances will end up sharing
            # the same dict.  So here it is added to the class to emphasize that
            # this is shared across all test cases in the class.
            cls.__gradescope__ = {}

        cls.__gradescope__[self._testMethodName] = {
            "weight": get_weight(*args, **kwargs),
            "score": None,
        }

        # Inject a set_score method into the test case instance.
        self.set_score = set_score

        # Add a function to process the gradescope variables.  This will be
        # called automatically after the test case is run().
        self.addCleanup(set_gradescope_vars, self)

        return func(self, *args, **kwargs)

    return wrapper
