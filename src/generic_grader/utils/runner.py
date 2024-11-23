
import base64
import json
import marshal
import os
import sys
import types
import warnings
from io import StringIO

from attrs import define, evolve, field

from generic_grader.utils.exceptions import (
    EndOfInputError,
    LogLimitExceededError,
)
from generic_grader.utils.options import Options
from generic_grader.utils.patches import custom_stack

""""
Tests that need things added still
func_not_defined # Possibly okay? Just need to expect an attribute error
random_function_calls
ocr_words_match_reference

pixel_overlap
plot_prop_matches_reference

all class tests



"""


def func_to_json(func_name, func):
    """Take in a function and return the base64 string of its marshal decoding in utf-8"""

    # func_source = base64.b64encode(marshal.dumps(func.__code__, 0)).decode()
    func_source = marshal.dumps(func.__code__, 0)
    func_b64_bin = base64.b64encode(func_source)
    func_b64_utf8 = func_b64_bin.decode()

    return func_name, func_b64_utf8


@define
class RunnerOptions:
    runs: int = field(converter=int, default=1)
    module: str = ""
    obj_name: str = ""
    files: tuple[str, ...] = field(converter=tuple, default=())
    turtle_test: bool = field(converter=bool, default=False)
    persistant_files: bool = field(converter=bool, default=False)
    import_options: Options = Options()
    call_options: Options = Options()


class Importer:
    """
    A Class for importing an object and handling errors.
    """

    class InputError(Exception):
        """Custom Exception type."""

    @classmethod
    def raise_input_error(cls):
        """Raise our custom exception."""
        raise cls.InputError()

    @classmethod
    def import_obj(cls, o: RunnerOptions):
        """
        Import the requested object from the module and return it.
        """
        with custom_stack(o.import_options):
            # Try to import student's object

            imp_obj = getattr(
                __import__("jack_test", fromlist=[o.obj_name]), o.obj_name
            )

        return imp_obj

    @classmethod
    def handle_error(cls, error, o: RunnerOptions):
        """
        Handle known errors and return the corresponding message.
        """
        match error:
            case cls.InputError():
                error_type = "InputError"
                error_text = (
                    f"Stuck at call to `input()` while importing `{o.obj_name}`."
                    "\n\nHint:\n"
                    "Avoid calling `input()` in the global scope "
                    "(i.e. outside of any function or other code block)."
                )
            case AttributeError():
                error_type = "AttributeError"
                error_text = (
                    f"Unable to import `{o.obj_name}`."
                    "\n\nHint:\n"
                    f"Define `{o.obj_name}` in your `{o.module}` module, and make"
                    " sure its definition is not inside of any other block."
                )
            case ModuleNotFoundError():
                module_name = str(error).split("'")[1]
                error_type = "ModuleNotFoundError"
                error_text = (
                    f"Unable to import `{module_name}`."
                    "\n\nHint:\n"
                    f"Make sure that you have submitted the correct file."
                    if o.module == module_name
                    else f"Make sure that {module_name} is a module that you can import from."
                )
            case _:
                error_type = type(error).__name__
                error_text = str(error)

        return error_type, error_text


class Runner:
    def __init__(self):
        try:
            with open("runner_input.json") as f:
                options = json.load(f)
        except FileNotFoundError:
            with open("runner_output.json", "w") as f:
                json.dump({"error": "runner_input.json not found"}, f)
            os._exit(1)

        try:
            module = options["module"]
            obj_name = options["obj_name"]
        except KeyError:
            with open("runner_output.json", "w") as f:
                json.dump({"error": "module and obj_name are required"}, f)
            os._exit(1)

        self.log = self.LogIO(options.get("log_limit", 0))
        entries = options.get("entries", [])
        self.interactions = []
        temp_patches = options.get("patches", [])

        built_patches = []
        for func_name in temp_patches:
            if temp_patches[func_name]["default"] is True:
                func_source = marshal.loads(
                    base64.b64decode(temp_patches[func_name]["source"])
                )
                func = types.FunctionType(func_source, globals())
                built_patches.append({"args": [f"{module}.{func_name}", func]})

        fixed_time = options.get("fixed_time", False)
        time_limit = options.get("time_limit", 1)
        memory_limit = options.get("memory_limit", 1.4)
        args = options.get("args", tuple())
        kwargs = options.get("kwargs", dict())
        init = options.get("init", None)
        turtle_test = options.get("turtle_test", False)
        runs = options.get("runs", 1)
        persistant_files = options.get("persistant_files", False)
        files_to_read = options.get("filenames", [])

        import_patches = built_patches.copy()
        import_patches.extend(
            [{"args": ["builtins.input", Importer.raise_input_error]}]
        )

        import_options = Options(
            fixed_time=fixed_time,
            time_limit=time_limit,
            memory_limit_GB=memory_limit,
            args=args,
            kwargs=kwargs,
            init=init,
            patches=import_patches,
            entries=entries,
        )
        built_patches.extend(
            [
                {"args": ["sys.stdout", self.log]},
                {"args": ["builtins.input", self.responder]},
            ]
        )
        call_options = evolve(import_options, patches=built_patches)

        self.runner_options = RunnerOptions(
            runs=runs,
            turtle_test=turtle_test,
            persistant_files=persistant_files,
            files=files_to_read,
            module=module,
            obj_name=obj_name,
            import_options=import_options,
            call_options=call_options,
        )
        """
        os.remove("runner_input.json")
        # Makes it slightly harder for students to see input
        """

    class LogIO(StringIO):
        """A string io object with a character limit."""

        def __init__(self, log_limit=0):
            """Initialize with an unlimited default limit (0 characters)."""
            super().__init__()
            self.log_limit = log_limit

        def __len__(self):
            """Return the number of characters in the log."""
            return len(self.getvalue())

        def write(self, s):
            """Wrap inherited `write()` with a length limit check."""
            super().write(s)

            # Check if limit is exceeded after write so the offending string
            # will be in the log for debugging.
            if self.log_limit and len(self) > self.log_limit:
                raise LogLimitExceededError()

    def responder(self, string=""):
        """Override for builtin input to provide simulated user responses."""
        # Save the IO stream location
        self.interactions.append(self.log.tell())

        # Log prompt
        self.log.write(string)

        try:
            entry = str(next(self.entries))
        except StopIteration as e:
            # Chain StopIteration to custom EndOfInputError which can be
            # handled later.
            raise EndOfInputError from e

        # Log entry
        self.log.write(entry + "\n")

        return entry

    def call_obj(self):
        """
        This is responsible for running a file and tracking everything that happens.
        It assumes the following:
            1. It is in the same directory as the file to be run.
            2. A file called `runner_input.json` exists in the same directory
                with all of the options required.
        """

        error_text = None
        error_type = None
        try:
            imported_object = Importer.import_obj(self.runner_options)

        except Exception as e:
            error_type, error_text = Importer.handle_error(e, self.runner_options)
            with open("runner_output.json", "w") as f:
                json.dump({"error": error_text, "error_type": error_type}, f)
            os._exit(1)

        json_output = dict()
        files_to_read = set(
            self.runner_options.files
        )  # This is so that even if we want to keep the file between runs we can still read it
        call_options = self.runner_options.call_options
        for attempt in range(self.runner_options.runs):
            self.entries = iter(call_options.entries)
            current_files = os.listdir()
            warning_list = []
            if call_options.init:
                call_options.init(self, attempt)  # temp

            with custom_stack(call_options):
                try:
                    with warnings.catch_warnings(record=True) as warning_list:
                        # This allows us to catch the warning for when files are left open
                        warnings.simplefilter("always")

                        return_value = imported_object(
                            *call_options.args, **call_options.kwargs
                        )

                except Exception as e:  # Temp
                    with open("runner_output.json", "w") as f:
                        json_output["error"] = str(e)
                        with open("runner_output.json", "w") as f:
                            json.dump(
                                json_output,
                                f,
                                indent=4,
                            )
                    os._exit(1)

            new_files = [file for file in os.listdir() if file not in current_files]
            files_to_read.update(new_files)
            new_files_content = dict()
            for file in files_to_read:
                try:
                    with open(file, "r") as f:
                        new_files_content[file] = f.read()
                    if (
                        not self.runner_options.persistant_files
                    ):  # We sometimes want to keep the file between runs (Final Project)
                        os.remove(file)
                except FileNotFoundError:
                    new_files_content[file] = None

            json_output[str(attempt)] = {
                "log": self.log.getvalue(),
                "interactions": self.interactions,
                "return_value": return_value,
                "new_files": new_files_content,
                "warnings": [str(warning.message) for warning in warning_list],
            }
            # Reset the log and interactions for the next run
            self.log.seek(0)
            self.log.truncate(0)
            self.interactions = []
        with open("runner_output.json", "w") as f:
            json.dump(
                json_output,
                f,
                indent=4,
            )

        # os._exit(0)

    @classmethod
    def cli_interface(cls):
        if "" not in sys.path:
            sys.path.insert(0, "")
        runner = Runner()

        if runner.runner_options.turtle_test is False:
            runner.call_obj()
