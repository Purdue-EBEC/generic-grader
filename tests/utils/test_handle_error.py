"""Tests for handle_error traceback filtering.

Issue #163: Grader machinery frames (e.g., from generic_grader package)
leak into student-facing tracebacks when generic-grader is installed
in a virtualenv where paths don't contain '/usr' or '/tests'.
"""

import traceback
from unittest.mock import patch

from generic_grader.utils.exceptions import handle_error


def _make_frame_summaries(filenames):
    """Create a list of FrameSummary objects with the given filenames.

    Each frame simulates a stack frame at the specified file path with
    a line number and function name.
    """
    return [
        traceback.FrameSummary(fn, lineno=i + 1, name=f"func_{i}")
        for i, fn in enumerate(filenames)
    ]


def _raise_with_filenames(filenames):
    """Create a real exception and patch extract_tb to return controlled frames.

    This lets us test handle_error's filtering logic with arbitrary
    file paths without needing to construct real traceback objects.
    """
    try:
        raise KeyError("test")
    except KeyError as e:
        frames = _make_frame_summaries(filenames)
        with patch(
            "generic_grader.utils.exceptions.traceback.extract_tb", return_value=frames
        ):
            return handle_error(e, "\nError message.")


class TestHandleErrorFiltering:
    """Test that handle_error filters out grader machinery frames."""

    def test_filters_tests_directory_frames(self):
        """Frames from /tests directories should be filtered out."""
        result = _raise_with_filenames(
            [
                "/autograder/source/tests/test_something.py",
                "/autograder/source/submission/student.py",
            ]
        )
        assert "test_something.py" not in result
        assert "student.py" in result

    def test_filters_usr_directory_frames(self):
        """Frames from /usr directories (system Python) should be filtered out."""
        result = _raise_with_filenames(
            [
                "/usr/lib/python3.13/ast.py",
                "/autograder/source/submission/student.py",
            ]
        )
        assert "ast.py" not in result
        assert "student.py" in result

    def test_filters_string_filename(self):
        """Frames from <string> (dynamically compiled code) should be filtered out."""
        result = _raise_with_filenames(
            [
                "<string>",
                "/autograder/source/submission/student.py",
            ]
        )
        assert 'File "<string>"' not in result
        assert "student.py" in result

    def test_filters_generic_grader_virtualenv_frames(self):
        """Frames from generic_grader package in a virtualenv should be filtered.

        This is the core bug from issue #163: when generic-grader is
        installed via uv into a virtualenv, paths like
        /autograder/source/.venv/lib/.../generic_grader/utils/user.py
        don't contain '/tests' or '/usr', so they leak through.
        """
        result = _raise_with_filenames(
            [
                "/autograder/source/.venv/lib/python3.13/site-packages/generic_grader/utils/user.py",
                "/autograder/source/submission/course_info.py",
            ]
        )
        assert "user.py" not in result
        assert "course_info.py" in result

    def test_filters_generic_grader_editable_install_frames(self):
        """Frames from generic_grader in an editable install should be filtered."""
        result = _raise_with_filenames(
            [
                "/autograder/source/generic_grader/utils/user.py",
                "/autograder/source/submission/student.py",
            ]
        )
        assert "user.py" not in result
        assert "student.py" in result

    def test_keeps_only_student_code_frames(self):
        """Only student code frames should remain in the traceback.

        Simulates the exact scenario from issue #163: a student's
        course_info.py raises a KeyError, and the traceback should
        show only their frame.
        """
        result = _raise_with_filenames(
            [
                "/autograder/source/.venv/lib/python3.13/site-packages/generic_grader/utils/user.py",
                "/autograder/source/submission/course_info.py",
                "/autograder/source/.venv/lib/python3.13/site-packages/generic_grader/utils/patches.py",
            ]
        )
        assert "user.py" not in result
        assert "patches.py" not in result
        assert "course_info.py" in result
        assert "Traceback (most recent call last):" in result

    def test_empty_traceback_when_all_frames_filtered(self):
        """When all frames are internal, no traceback header should appear."""
        result = _raise_with_filenames(
            [
                "/autograder/source/tests/test_something.py",
                "/usr/lib/python3.13/something.py",
            ]
        )
        assert "Traceback (most recent call last):" not in result
        # But the exception itself should still appear
        assert "KeyError" in result

    def test_strips_path_from_student_frames(self):
        """Student frame filenames should have directory paths removed."""
        result = _raise_with_filenames(
            [
                "/autograder/source/submission/my_program.py",
            ]
        )
        # The full path should not appear
        assert "/autograder/source/submission/" not in result
        # But the filename should
        assert "my_program.py" in result


class TestHandleErrorSyntaxError:
    """Test SyntaxError special handling in handle_error."""

    def test_syntax_error_path_stripped(self):
        """SyntaxError.filename should have its directory path removed."""
        try:
            raise SyntaxError(
                "invalid syntax",
                ("/autograder/source/submission/student.py", 5, 10, "x = "),
            )
        except SyntaxError as e:
            frames = _make_frame_summaries(
                ["/autograder/source/tests/test_something.py"]
            )
            with patch(
                "generic_grader.utils.exceptions.traceback.extract_tb",
                return_value=frames,
            ):
                result = handle_error(e, "\nSyntax error in your code.")
            assert "/autograder/source/submission/" not in result
            assert "student.py" in result

    def test_syntax_error_with_generic_grader_path(self):
        """SyntaxError from within generic_grader should also be handled."""
        try:
            raise SyntaxError(
                "invalid syntax",
                (
                    "/autograder/source/.venv/lib/python3.13/site-packages/generic_grader/utils/something.py",
                    5,
                    10,
                    "x = ",
                ),
            )
        except SyntaxError as e:
            frames = _make_frame_summaries(
                [
                    "/autograder/source/.venv/lib/python3.13/site-packages/generic_grader/utils/something.py"
                ]
            )
            with patch(
                "generic_grader.utils.exceptions.traceback.extract_tb",
                return_value=frames,
            ):
                result = handle_error(e, "\nSyntax error.")
            # The generic_grader path should be stripped
            assert "site-packages" not in result


class TestHandleErrorOutput:
    """Test the output format of handle_error."""

    def test_output_is_indented(self):
        """The output should be indented with two spaces."""
        result = _raise_with_filenames(["/autograder/source/submission/student.py"])
        # Each line should start with two spaces (indent function)
        for line in result.splitlines():
            assert line.startswith("  "), f"Line not indented: {line!r}"

    def test_error_msg_appears_in_output(self):
        """The error_msg parameter should appear in the output."""
        result = _raise_with_filenames(["/autograder/source/submission/student.py"])
        assert "Error message." in result

    def test_exception_type_appears_in_output(self):
        """The exception type and message should appear in the output."""
        result = _raise_with_filenames(["/autograder/source/submission/student.py"])
        assert "KeyError" in result
