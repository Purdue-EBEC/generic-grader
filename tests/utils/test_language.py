"""Unit tests for :mod:`generic_grader.utils.language`."""

from __future__ import annotations

from dataclasses import dataclass

from generic_grader.utils.language import LANGUAGE_EXTENSIONS, resolve_language


@dataclass
class _Opts:
    language: str | None = None


def test_language_extensions_covers_both_supported_languages():
    assert LANGUAGE_EXTENSIONS == {"python": ".py", "octave": ".m"}


def test_resolve_language_defaults_to_python_when_missing():
    class NoLang:
        pass

    assert resolve_language(NoLang()) == "python"


def test_resolve_language_defaults_to_python_for_none():
    assert resolve_language(_Opts(language=None)) == "python"


def test_resolve_language_defaults_to_python_for_empty_string():
    assert resolve_language(_Opts(language="")) == "python"


def test_resolve_language_returns_explicit_value():
    assert resolve_language(_Opts(language="octave")) == "octave"
    assert resolve_language(_Opts(language="python")) == "python"
