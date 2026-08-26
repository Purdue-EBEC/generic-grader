"""Cross-module tests that every Python-only test type refuses to run
under ``language="octave"``.

Instead of adding a near-identical file under each ``tests/<domain>``,
this suite drives the ``build`` factory from each guarded module,
instantiates the resulting ``TestCase`` with a parametrized name, and
asserts the test raises ``AssertionError`` with the shared
language-guard message.  If someone later adds a new Python-only test
type they should extend :data:`GUARDED_CASES` here so the coverage
guard fails until the module gets the ``require_python_language``
call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pytest

from generic_grader.class_.class_attributes_match_reference import (
    build as build_class_attributes,
)
from generic_grader.class_.class_is_defined import build as build_class_is_defined
from generic_grader.class_.class_method_signatures_match_reference import (
    build as build_class_method_signatures,
)
from generic_grader.class_.instance_attributes_match_reference import (
    build as build_instance_attributes,
)
from generic_grader.file.file_closed import build as build_file_closed
from generic_grader.function.function_not_defined import (
    build as build_function_not_defined,
)
from generic_grader.function.random_function_calls import (
    build as build_random_function_calls,
)
from generic_grader.image.ocr_words_match_reference import (
    build as build_ocr_words_match_reference,
)
from generic_grader.image.pixel_overlap import build as build_pixel_overlap
from generic_grader.utils.options import Options


@dataclass(frozen=True)
class GuardedCase:
    """Description of one guarded test type.

    ``method_name`` matches the parametrized method emitted by
    ``parameterized.expand`` for the first (index ``0``) case; the
    docstring guard uses ``test_docstring_module`` because that method
    is the first one exposed by :mod:`~generic_grader.style.docstring`.
    """

    label: str  # used only for readable pytest output
    build: Callable[[Options], type]
    method_name: str
    expected_fragment: str  # substring the failure message must contain
    extra_options: dict


GUARDED_CASES: list[GuardedCase] = [
    GuardedCase(
        label="class_.class_attributes_match_reference",
        build=build_class_attributes,
        method_name="test_class_attributes_match_reference_0",
        expected_fragment="class_.class_attributes_match_reference",
        extra_options={},
    ),
    GuardedCase(
        label="class_.class_is_defined",
        build=build_class_is_defined,
        method_name="test_class_is_defined_0",
        expected_fragment="class_.class_is_defined",
        extra_options={},
    ),
    GuardedCase(
        label="class_.class_method_signatures_match_reference",
        build=build_class_method_signatures,
        method_name="test_class_method_signatures_match_reference_0",
        expected_fragment="class_.class_method_signatures_match_reference",
        extra_options={},
    ),
    GuardedCase(
        label="class_.instance_attributes_match_reference",
        build=build_instance_attributes,
        method_name="test_instance_attributes_match_reference_0",
        expected_fragment="class_.instance_attributes_match_reference",
        extra_options={},
    ),
    GuardedCase(
        label="function.function_not_defined",
        build=build_function_not_defined,
        method_name="test_function_not_defined_0",
        expected_fragment="function.function_not_defined",
        extra_options={},
    ),
    GuardedCase(
        label="function.random_function_calls",
        build=build_random_function_calls,
        method_name="test_random_function_calls_0",
        expected_fragment="function.random_function_calls",
        extra_options={},
    ),
    GuardedCase(
        label="file.file_closed",
        build=build_file_closed,
        method_name="test_file_closed_0",
        expected_fragment="file.file_closed",
        extra_options={},
    ),
    GuardedCase(
        label="image.ocr_words_match_reference",
        build=build_ocr_words_match_reference,
        method_name="test_ocr_words_match_reference_0",
        expected_fragment="image.ocr_words_match_reference",
        extra_options={"expected_words": "hi"},
    ),
    GuardedCase(
        label="image.pixel_overlap",
        build=build_pixel_overlap,
        method_name="test_pixel_overlap_0",
        expected_fragment="image.pixel_overlap",
        extra_options={},
    ),
]


@pytest.mark.parametrize("case", GUARDED_CASES, ids=lambda c: c.label)
def test_python_only_test_types_reject_octave_language(case, fix_syspath):
    """The test method must fail with the shared language-guard message."""

    options = Options(
        sub_module="sub",
        ref_module="ref",
        obj_name="do_stuff",
        weight=1,
        language="octave",
        **case.extra_options,
    )
    built_class = case.build(options)

    instance = built_class(methodName=case.method_name)
    with pytest.raises(AssertionError) as exc:
        getattr(instance, case.method_name)()

    message = str(exc.value)
    assert "Python-only" in message
    assert case.expected_fragment in message
    assert "'octave'" in message


def test_python_language_is_still_reachable_for_a_guarded_test(fix_syspath):
    """Sanity check: the guard doesn't fire for the default language.

    Uses ``function.function_not_defined`` because it has the smallest
    surface \u2014 no need to create a submission module or a plot.  The
    test itself is expected to *pass* here because ``sub.py`` genuinely
    does not define ``missing_func``.
    """

    (fix_syspath / "sub.py").write_text("pass\n")
    options = Options(sub_module="sub", obj_name="missing_func", weight=1)
    built_class = build_function_not_defined(options)
    instance = built_class(methodName="test_function_not_defined_0")
    # Should complete without raising.
    instance.test_function_not_defined_0()
