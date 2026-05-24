"""IPC protocol between the grader (host) and the sandboxed worker.

Wire format
-----------

A *frame* is a decimal byte length, a single newline, then exactly that
many bytes of payload::

    18\\n{"hello": "world"}

This keeps newlines inside the JSON payload (e.g. captured `print`
output containing ``\\n``) from corrupting frame boundaries.

A *request* is a single framed JSON object sent from host to worker.
A *response* is a single framed JSON object sent the other way. There
is no streaming: the host writes one request, the worker writes one
response, both processes exit (the worker is restarted under a fresh
sandbox for the next test).

Envelopes
---------

`Request` carries everything the worker needs to run the test:
runtime selector, submission directory, module name, callable to invoke,
positional / keyword arguments, simulated stdin entries, resource
limits, fixed time, and a `captures` whitelist that lets the host
opt particular event types in or out (so e.g. plot tests can skip
stdout capture overhead).

`Response` carries an ordered list of `Event` records, an `elapsed_seconds`
float, and an optional `exception` chain (one entry per link of the
chain; each entry has type, message, and a sanitized traceback string).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Iterable

PROTOCOL_VERSION = 1

_DEFAULT_CAPTURES = ("stdout", "stderr", "return", "figures", "exception")


class SandboxException(Exception):
    """Raised on any protocol-level error (framing, version mismatch, …).

    Worker-side or host-side translation of *student* exceptions does
    *not* use this class; those are serialized into the response body
    as a structured `exception` chain.
    """

    @staticmethod
    def serialized_chain(chain):
        """Identity helper for readability at call sites.

        The chain is just a list of dicts at the wire level; this method
        exists so callers can write `SandboxException.serialized_chain(...)`
        and convey intent.  It performs no transformation.
        """
        return list(chain)


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def write_frame(stream: BinaryIO, payload: bytes) -> None:
    """Write a length-prefixed frame to a binary stream."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    header = f"{len(payload)}\n".encode("ascii")
    stream.write(header)
    stream.write(payload)
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()


def read_frame(stream: BinaryIO) -> bytes | None:
    """Read a single framed payload from `stream`.

    Returns ``None`` on a clean EOF (no bytes available).  Raises
    `SandboxException` if the framing is malformed (non-decimal length,
    negative length, or a truncated payload).
    """
    header = bytearray()
    while True:
        ch = stream.read(1)
        if not ch:
            if not header:
                return None
            raise SandboxException(
                "Truncated frame: EOF reached before length terminator"
            )
        if ch == b"\n":
            break
        header.extend(ch)
        if len(header) > 20:  # decimal length can't exceed this many digits
            raise SandboxException(f"Invalid frame length header: {bytes(header)!r}")

    try:
        length = int(header.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as e:
        raise SandboxException(f"Invalid frame length header: {bytes(header)!r}") from e
    if length < 0:
        raise SandboxException(f"Negative frame length: {length}")

    payload = stream.read(length)
    if len(payload) != length:
        raise SandboxException(
            f"Truncated frame: expected {length} bytes, got {len(payload)}"
        )
    return bytes(payload)


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


@dataclass
class Event:
    """A single thing the worker observed while running submitted code.

    Common types:
      - ``"stdout"`` / ``"stderr"``: ``data`` is a str chunk.
      - ``"stdin"``: ``data`` is the line consumed by ``input()``.
      - ``"return"``: ``value`` is the return value (must be JSON-serializable).
      - ``"figure"``: ``properties`` is a serialized representation of a
        Matplotlib figure produced by `python_runtime.serialize_figure`.

    Unknown payload fields are preserved as-is so the protocol can grow
    without breaking older readers.
    """

    type: str
    extra: dict[str, Any] = field(default_factory=dict)

    def __init__(self, type: str, **payload: Any) -> None:  # noqa: A002
        self.type = type
        self.extra = dict(payload)

    # The dataclass-generated __eq__ would compare on `type` and `extra`;
    # we want to compare on the merged dict so two Events constructed
    # with the same kwargs in different orders compare equal.
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Event):
            return NotImplemented
        return self.type == other.type and self.extra == other.extra

    def __repr__(self) -> str:
        kw = ", ".join(f"{k}={v!r}" for k, v in self.extra.items())
        return f"Event(type={self.type!r}{', ' + kw if kw else ''})"

    def to_dict(self) -> dict[str, Any]:
        out = {"type": self.type}
        out.update(self.extra)
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        d = dict(d)
        type_ = d.pop("type")
        return cls(type_, **d)

    # Allow attribute access for documented payload fields used at call sites.
    def __getattr__(self, name: str) -> Any:
        try:
            return self.__dict__["extra"][name]
        except KeyError as e:
            raise AttributeError(name) from e


# ---------------------------------------------------------------------------
# Request envelope
# ---------------------------------------------------------------------------


@dataclass
class Request:
    runtime: str
    submission_dir: str
    module: str
    obj_name: str
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    entries: tuple = ()
    fixed_time: str | None = None
    time_limit_seconds: float = 1.0
    memory_limit_mb: int = 1400
    log_limit: int = 0
    captures: tuple = _DEFAULT_CAPTURES
    protocol_version: int = PROTOCOL_VERSION

    def to_json(self) -> str:
        return json.dumps(
            {
                "protocol_version": self.protocol_version,
                "runtime": self.runtime,
                "submission_dir": self.submission_dir,
                "module": self.module,
                "obj_name": self.obj_name,
                "args": list(self.args),
                "kwargs": self.kwargs,
                "entries": list(self.entries),
                "fixed_time": self.fixed_time,
                "time_limit_seconds": self.time_limit_seconds,
                "memory_limit_mb": self.memory_limit_mb,
                "log_limit": self.log_limit,
                "captures": list(self.captures),
            }
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Request":
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SandboxException(f"Invalid request JSON: {e}") from e
        version = d.get("protocol_version")
        if version != PROTOCOL_VERSION:
            raise SandboxException(
                f"Unsupported protocol_version {version!r}; expected {PROTOCOL_VERSION}"
            )
        required = ("runtime", "submission_dir", "module", "obj_name")
        for key in required:
            if key not in d:
                raise SandboxException(f"Request missing required field: {key!r}")
        return cls(
            runtime=d["runtime"],
            submission_dir=d["submission_dir"],
            module=d["module"],
            obj_name=d["obj_name"],
            args=tuple(d.get("args", ())),
            kwargs=d.get("kwargs", {}) or {},
            entries=tuple(d.get("entries", ())),
            fixed_time=d.get("fixed_time"),
            time_limit_seconds=d.get("time_limit_seconds", 1.0),
            memory_limit_mb=d.get("memory_limit_mb", 1400),
            log_limit=d.get("log_limit", 0),
            captures=tuple(d.get("captures", _DEFAULT_CAPTURES)),
        )


def write_request(stream: BinaryIO, request: Request) -> None:
    write_frame(stream, request.to_json().encode("utf-8"))


def read_request(stream: BinaryIO) -> Request | None:
    frame = read_frame(stream)
    if frame is None:
        return None
    return Request.from_json(frame)


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


@dataclass
class Response:
    events: list[Event] = field(default_factory=list)
    exception: list[dict[str, Any]] | None = None
    elapsed_seconds: float = 0.0
    protocol_version: int = PROTOCOL_VERSION

    def to_json(self) -> str:
        return json.dumps(
            {
                "protocol_version": self.protocol_version,
                "events": [e.to_dict() for e in self.events],
                "exception": self.exception,
                "elapsed_seconds": self.elapsed_seconds,
            }
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Response":
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SandboxException(f"Invalid response JSON: {e}") from e
        version = d.get("protocol_version")
        if version != PROTOCOL_VERSION:
            raise SandboxException(
                f"Unsupported protocol_version {version!r}; expected {PROTOCOL_VERSION}"
            )
        return cls(
            events=[Event.from_dict(ev) for ev in d.get("events", [])],
            exception=d.get("exception"),
            elapsed_seconds=d.get("elapsed_seconds", 0.0),
        )


def write_response(stream: BinaryIO, response: Response) -> None:
    write_frame(stream, response.to_json().encode("utf-8"))


def read_response(stream: BinaryIO) -> Response | None:
    frame = read_frame(stream)
    if frame is None:
        return None
    return Response.from_json(frame)


__all__: Iterable[str] = (
    "PROTOCOL_VERSION",
    "Event",
    "Request",
    "Response",
    "SandboxException",
    "read_frame",
    "read_request",
    "read_response",
    "write_frame",
    "write_request",
    "write_response",
)
