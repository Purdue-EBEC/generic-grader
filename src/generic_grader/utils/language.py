"""Small helpers for language-aware test dispatch.

Keeping this in one tiny module avoids scattering
``getattr(options, "language", "python") or "python"`` and the
``.py`` / ``.m`` extension map across every style / function test.
"""

from __future__ import annotations

# Canonical file extension per supported language.  Extension includes
# the leading dot so callers can concatenate directly onto a path.
LANGUAGE_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "octave": ".m",
}


def resolve_language(options) -> str:
    """Return the language string on *options*, defaulting to ``"python"``.

    A missing attribute, ``None``, or empty string all resolve to
    ``"python"`` so callers can treat the return value as always
    populated.
    """

    language = getattr(options, "language", None) or "python"
    return language
