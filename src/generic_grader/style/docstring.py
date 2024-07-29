"""Test program docstring."""

import ast
import datetime
import os
import textwrap
import unittest


def parse_docstring(docstring):
    """Parse the doc string to find required components."""

    author, assignment, date = None, None, None
    description, contributors, integrity = [], [], []

    part = None
    for line in docstring.split("\n"):
        line = line.strip()

        if line.startswith("Author:"):
            author = line.replace("Author:", "").strip()
            part = None
        elif line.startswith("Assignment:"):
            assignment = line.replace("Assignment:", "").strip()
            part = None
        elif line.startswith("Date:"):
            date = line.replace("Date:", "").strip()
            part = None
        elif line.startswith("Description"):
            part = "Description"
        elif line.startswith("Contributors"):
            part = "Contributors"
        elif line.startswith("Academic Integrity Statement"):
            part = "Integrity"
        elif part == "Description":
            description.append(line)
        elif part == "Contributors":
            contributors.append(line)
        elif part == "Integrity":
            integrity.append(line)

    return author, assignment, date, description, contributors, integrity


def titlecase(phrase):
    return " ".join(word.capitalize() for word in phrase.split())


def build(options):
    submission = options.sub_module.replace(".", os.path.sep) + ".py"
    reference = options.ref_module.replace(".", os.path.sep) + ".py"

    class TestDocstring(unittest.TestCase):
        """A class for docstring tests."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        def setUp(self):
            with open(submission) as fo:
                fail_msg = None
                try:
                    self.doc = ast.get_docstring(ast.parse(fo.read()))
                except SyntaxError as e:
                    fail_msg = (
                        f"Error while parsing `{submission}`. "
                        + f'The error was "{e.__class__.__name__}: {e}".'
                    )
                # Fail outside of the except block
                # so that AssertionError(s) will be handled properly.
                if fail_msg:
                    self.fail(fail_msg)
            (
                self.author,
                self.assignment,
                self.date,
                self.description,
                self.contributors,
                self.integrity,
            ) = parse_docstring(self.doc or "")

        def test_docstring_module(self):
            """Check for existence of module level docstring."""

            message = "\n\nHint:\n" + self.wrapper.fill(
                "The program's docstring was not found."
                "  A docstring is the first triple quoted string"
                ' (e.g. """program description ...""") in a Python program,'
                " and should appear before any code."
                "  Make sure to include the docstring"
                " from the provided Python program template"
                " at the top of your program."
            )
            self.assertIsNotNone(self.doc, msg=message)

        def test_docstring_author(self):
            """Check assignment author exists."""

            actual = self.author and len(self.author) or 0
            minimum = 2
            message = "\n\nHint:\n" + self.wrapper.fill(
                "The author's name was not found."
                "  Make sure you have included your name and email address"
                ' on the "Author:" line of the docstring'
                ' (e.g. "Author: Your Name, login@purdue.edu").'
            )
            self.assertGreaterEqual(actual, minimum, msg=message)

            message = "\n\nHint:\n" + self.wrapper.fill(
                "The author's email address was not found."
                "  Make sure you have included your name and email address"
                ' on the "Author:" line of the docstring'
                ' (e.g. "Author: Your Name, login@purdue.edu").'
            )
            self.assertIn("@purdue.edu", self.author.lower(), msg=message)

        def test_docstring_assignment_name(self):
            """Check assignment name exists."""

            name = titlecase(submission.replace(".py", "").replace("_", " "))
            actual = self.assignment and len(self.assignment) or 0
            minimum = 7
            message = "\n\nHint:\n" + self.wrapper.fill(
                "The assignment's name was not found."
                "  Make sure you have included the name of this assignment"
                ' on the "Assignment:" line of the docstring'
                f' (e.g. "Assignment: mm.n - {name}").'
            )
            self.assertGreaterEqual(actual, minimum, msg=message)

            message = "\n\nHint:\n" + self.wrapper.fill(
                "The assignment name doesn't match the required name."
                "  Make sure you have included the assignment name"
                ' on the "Assignment:" line of the docstring '
                f'(e.g. "Assignment: mm.n - {name}").'
            )
            self.assertIn(name.lower(), self.assignment.lower(), msg=message)

        def test_docstring_date(self):
            """Check assignment date exists."""

            actual = self.date and len(self.date) or 0
            minimum = 8  # e.g. "01/01/22"
            today = datetime.datetime.today().date().isoformat()
            message = "\n\nHint:\n" + self.wrapper.fill(
                "The program's date was not found."
                "  Make sure you have included this program's completion date"
                f' on the "Date:" line of the docstring (e.g. "Date: {today}").'
            )
            self.assertGreaterEqual(actual, minimum, msg=message)

        def test_docstring_desc(self):
            """Check description length of module level docstring."""

            actual = len("".join(self.description))
            with open(reference) as fo:
                reference_doc = ast.get_docstring(ast.parse(fo.read()))
            _, _, _, reference_desc, _, _ = parse_docstring(reference_doc)
            minimum = len("".join(reference_desc)) // 2
            maximum = len("".join(reference_desc)) * 5

            message = "\n\nHint:\n" + self.wrapper.fill(
                "The program's description was not found."
                "  Make sure you have included a description of your program"
                ' after the "Description:" heading in the docstring,'
                ' and that "Description:" is spelled correctly.'
            )
            self.assertNotEqual(actual, 0, msg=message)

            message = "\n\nHint:\n" + self.wrapper.fill(
                "The program's description is too short."
                "  Include a more detailed description"
                " of your program in the docstring."
            )
            self.assertGreaterEqual(actual, minimum, msg=message)

            message = "\n\nHint:\n" + self.wrapper.fill(
                "The program's description is too long."
                "  See if you can make your program"
                " description more concise."
            )
            self.assertLessEqual(actual, maximum, msg=message)

        def test_docstring_contributors(self):
            """Check contributors length of module level docstring."""

            actual = len("".join(self.contributors))
            minimum = 4  # e.g. "None"
            message = "\n\nHint:\n" + self.wrapper.fill(
                "The program contributors section is missing "
                "or too short.  Complete the contributors section, "
                'even if it is "None".'
            )

            self.assertGreaterEqual(actual, minimum, msg=message)

        def test_docstring_integrity(self):
            """Check for academic integrity statement."""

            actual_integrity = "\n".join(self.integrity) + "\n"

            expected_integrity = "\n".join(
                [
                    "I have not used source code obtained from any unauthorized",
                    "source, either modified or unmodified; nor have I provided",
                    "another student access to my code.  The project I am",
                    "submitting is my own original work.\n",
                ]
            )

            message = "\n\nHint:\n" + self.wrapper.fill(
                "The Academic Integrity Statement is missing or modified."
                "  Please include this statement exactly as provided in the template."
            )

            self.maxDiff = None
            self.assertEqual(actual_integrity, expected_integrity, msg=message)

    return TestDocstring
