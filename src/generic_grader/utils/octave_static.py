"""Static analysis helpers for GNU Octave ``.m`` files.

These are the Octave counterparts to :mod:`generic_grader.utils.static`:
they let the style/loop tests run against ``.m`` submissions without
spawning a subprocess.  The functions all take a ``test`` argument
purely so they can call ``test.fail(...)`` with a friendly message
when the file is missing or unreadable \u2014 same convention as the
Python-side helpers.

Design notes
------------

* Octave accepts both ``%`` and ``#`` as line-comment markers.  Block
  comments are delimited by ``%{`` / ``%}`` (or ``#{`` / ``#}``) on
  their own lines.  Both forms are recognised here.
* String literals in Octave are wrapped in ``'`` or ``"``.  A ``%``
  or ``#`` inside a string is *not* a comment.  We strip strings
  before hunting for comment markers to avoid mistakes.
* The tokenizer is deliberately simple: after strings and comments
  are removed, whitespace-separated runs are tokens.  That gives the
  same order-of-magnitude "how big is this program?" signal that the
  Python token stream provides for :mod:`style.program_length`
  without pulling in a full Octave grammar.
* The loop-depth tracker walks the source line-by-line and matches
  ``for``/``while``/``do`` against ``end``/``endfor``/``endwhile``/
  ``until``.  It shares the same caveats the Python
  :class:`~generic_grader.utils.static.LoopDepthTracker` already
  documents \u2014 unreachable code inflates the count, and function
  calls that contain their own loops deflate it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# File I/O helpers                                                            #
# --------------------------------------------------------------------------- #


def read_source(test, file_name: str) -> str:
    """Return the text of ``file_name`` or fail *test* with a hint.

    Kept in its own tiny helper so every caller reports the same
    error message when a submission is missing.
    """

    try:
        with open(file_name, encoding="utf-8") as fo:
            return fo.read()
    except FileNotFoundError:
        test.fail(
            f"Unable to load `{file_name}`.\n\nHint:\n  Make sure you "
            f"have submitted a file named `{file_name}` in the top "
            f"level of your submission."
        )
    return ""  # pragma: no cover \u2014 unreachable after ``test.fail``


# --------------------------------------------------------------------------- #
# String / comment stripping                                                  #
# --------------------------------------------------------------------------- #

# A single-quoted or double-quoted Octave string literal.  Octave does
# NOT support backslash escapes inside single quotes; inside double
# quotes ``\"`` is an escape for a literal ``"``.  Both are handled
# here with a compact regex that matches balanced quotes on one line.
_STRING_LITERAL_RE = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"")


def _strip_string_literals(line: str) -> str:
    """Replace every string literal in *line* with a same-length blob of
    spaces so column positions are preserved while ``%``/``#`` inside
    strings no longer look like comment markers.
    """

    def blank(match: re.Match) -> str:
        return " " * (match.end() - match.start())

    return _STRING_LITERAL_RE.sub(blank, line)


def _strip_line_comment(line: str) -> tuple[str, str | None]:
    """Split *line* into ``(code, comment_text_or_None)``.

    ``comment_text_or_None`` is the text after the ``%``/``#`` marker
    (marker included) when there is one, otherwise ``None``.  The
    returned ``code`` still has its trailing whitespace stripped.
    """

    stripped = _strip_string_literals(line)
    m = re.search(r"[%#]", stripped)
    if m is None:
        return line.rstrip(), None
    col = m.start()
    comment_text = line[col:]
    return line[:col].rstrip(), comment_text


# --------------------------------------------------------------------------- #
# Comment extraction                                                          #
# --------------------------------------------------------------------------- #


def get_comments(test, file_name: str) -> tuple[list[str], list[str]]:
    """Return ``(header_comments, body_comments)`` from ``file_name``.

    Header comments are the contiguous run of leading comment lines
    (blank lines allowed) before the first line that contains any
    non-comment code.  Everything else counts as body.

    Block comments (``%{`` \u2026 ``%}``) are collected as a single string
    per block, matching the Python tokenizer's habit of returning one
    comment token per ``#``-delimited line.
    """

    src = read_source(test, file_name)

    header, body = [], []
    seen_code = False
    in_block = False
    block_buffer: list[str] = []

    for raw_line in src.splitlines():
        stripped = raw_line.strip()

        # Block-comment start / end \u2014 must be on their own line.
        if not in_block and stripped in ("%{", "#{"):
            in_block = True
            block_buffer = [stripped]
            continue
        if in_block:
            block_buffer.append(stripped)
            if stripped in ("%}", "#}"):
                joined = "\n".join(block_buffer)
                (body if seen_code else header).append(joined)
                in_block = False
            continue

        code, comment = _strip_line_comment(raw_line)
        if code:
            seen_code = True
            if comment is not None:
                body.append(comment)
        elif comment is not None:
            (body if seen_code else header).append(comment)

    return header, body


# --------------------------------------------------------------------------- #
# Token counting                                                              #
# --------------------------------------------------------------------------- #

# Matches Octave identifiers, numbers, and single-character operators.
# ``.`` inside a number keeps it as one token; operators like ``==``
# or ``~=`` count as one token each thanks to the eager alternation.
_TOKEN_RE = re.compile(
    r"""
    [A-Za-z_][A-Za-z_0-9]*        # identifier / keyword
  | \d+\.\d*(?:[eE][+-]?\d+)?     # 1.5 or 1e-3
  | \.\d+(?:[eE][+-]?\d+)?        # .5
  | \d+(?:[eE][+-]?\d+)?          # 42 or 1e3
  | ==|~=|!=|<=|>=|&&|\|\||\.\*|\./|\.\^|\.\'
  | \+\+|--|\+=|-=|\*=|/=
  | [(){}\[\],;:]
  | [+\-*/^=<>~!&|.'"]            # single-char ops / string quotes
    """,
    re.VERBOSE,
)


def get_tokens(test, file_name: str) -> list[str]:
    """Return every non-comment, non-whitespace token in ``file_name``.

    The result is a flat list of token strings, mirroring the
    interface of :func:`generic_grader.utils.static.get_tokens` closely
    enough that :mod:`style.program_length` can measure it with
    ``len(...)``.
    """

    src = read_source(test, file_name)

    tokens: list[str] = []
    in_block = False
    for raw_line in src.splitlines():
        stripped = raw_line.strip()
        if not in_block and stripped in ("%{", "#{"):
            in_block = True
            continue
        if in_block:
            if stripped in ("%}", "#}"):
                in_block = False
            continue

        code, _ = _strip_line_comment(raw_line)
        # Blank string literals before tokenizing so their contents
        # don't inflate the token count — the quote characters
        # themselves still count.
        code_no_strings = _strip_string_literals(code)
        tokens.extend(_TOKEN_RE.findall(code_no_strings))

    return tokens


# --------------------------------------------------------------------------- #
# Loop depth                                                                  #
# --------------------------------------------------------------------------- #

# Loop openers: ``for``/``parfor``/``while``/``do``.  We look for the
# keyword at the start of the token stream on a line (leading
# whitespace is allowed).  Trailing content is irrelevant.
_LOOP_OPEN_RE = re.compile(r"^\s*(for|parfor|while|do)\b")

# Loop-only closers.  A bare ``end`` closes anything that opened
# earlier, so we track the whole opener stack and match by kind.
_LOOP_CLOSE_RE = re.compile(r"^\s*(endfor|endwhile|end_try_catch|until)\b")

# ``end`` (plain) closes the top-of-stack opener.  We handle it
# separately because plain ``end`` also closes ``if``/``function``
# blocks that we push onto the stack too.
_GENERIC_OPEN_RE = re.compile(r"^\s*(if|switch|function|try|unwind_protect)\b")
_GENERIC_CLOSE_RE = re.compile(
    r"^\s*(end|endif|endswitch|endfunction|end_unwind_protect)\b"
)


@dataclass
class LoopDepthResult:
    """Structured result from :class:`LoopDepthTracker`.

    Mirrors :class:`generic_grader.utils.static.LoopDepthTracker`'s
    ``current_depth`` / ``max_depth`` attributes so the caller can
    read them the same way.
    """

    current_depth: int = 0
    max_depth: int = 0
    stack: list[str] = field(default_factory=list)


class LoopDepthTracker:
    """Very small state machine that walks Octave source line-by-line.

    Usage matches the AST-based tracker's callsite in
    :mod:`function.static_loop_depth`::

        tracker = LoopDepthTracker()
        tracker.visit_source(source_text)
        assert tracker.max_depth <= o.max_depth
    """

    LOOP_KINDS = {"for", "parfor", "while", "do"}
    NON_LOOP_BLOCK_KINDS = {"if", "switch", "function", "try", "unwind_protect"}

    def __init__(self) -> None:
        self.current_depth = 0
        self.max_depth = 0
        self._stack: list[str] = []

    def _push(self, kind: str) -> None:
        self._stack.append(kind)
        if kind in self.LOOP_KINDS:
            self.current_depth += 1
            self.max_depth = max(self.max_depth, self.current_depth)

    def _pop(self) -> None:
        if not self._stack:
            return  # unbalanced end \u2014 tolerate silently
        kind = self._stack.pop()
        if kind in self.LOOP_KINDS:
            self.current_depth -= 1

    def visit_source(self, source: str) -> "LoopDepthTracker":
        in_block = False
        for raw_line in source.splitlines():
            stripped = raw_line.strip()

            if not in_block and stripped in ("%{", "#{"):
                in_block = True
                continue
            if in_block:
                if stripped in ("%}", "#}"):
                    in_block = False
                continue

            code, _ = _strip_line_comment(raw_line)
            if not code.strip():
                continue

            m_loop = _LOOP_OPEN_RE.match(code)
            if m_loop:
                self._push(m_loop.group(1))
                continue

            m_generic_open = _GENERIC_OPEN_RE.match(code)
            if m_generic_open:
                self._push(m_generic_open.group(1))
                continue

            if _LOOP_CLOSE_RE.match(code) or _GENERIC_CLOSE_RE.match(code):
                self._pop()

        return self


# --------------------------------------------------------------------------- #
# Docstring extraction                                                        #
# --------------------------------------------------------------------------- #


def get_docstring(test, file_name: str) -> str | None:
    """Return the leading header-comment block, or ``None`` if absent.

    An Octave function/script file's "docstring" is by convention the
    contiguous run of comment lines at the top of the file, before
    any code and (optionally) before the ``function`` declaration.
    The returned string has the ``%``/``#`` markers stripped so it
    can be fed straight into
    :func:`generic_grader.style.docstring.parse_docstring`.
    """

    src = read_source(test, file_name)

    lines: list[str] = []
    seen_any = False
    in_block = False

    for raw_line in src.splitlines():
        stripped = raw_line.strip()

        # Skip a leading shebang or ``function`` declaration \u2014 both
        # can precede the docstring per Octave convention.
        if not seen_any and (
            stripped.startswith("#!") or stripped.startswith("function")
        ):
            continue

        # Blank lines above / between header comments are allowed.
        if not stripped:
            if lines:
                lines.append("")
                continue
            continue

        if not in_block and stripped in ("%{", "#{"):
            in_block = True
            continue
        if in_block:
            if stripped in ("%}", "#}"):
                in_block = False
                seen_any = True
                continue
            lines.append(stripped)
            continue

        # A real single-line comment?
        if stripped.startswith("%") or stripped.startswith("#"):
            # Strip the first marker (and one following space if any).
            cleaned = stripped.lstrip("%#")
            if cleaned.startswith(" "):
                cleaned = cleaned[1:]
            lines.append(cleaned)
            seen_any = True
            continue

        # First non-comment, non-blank line \u2014 stop.
        break

    if not lines:
        return None
    # Trim trailing blank lines to match ``ast.get_docstring`` behaviour.
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) if lines else None
