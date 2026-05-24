"""Tests for the sandbox IPC protocol (request/response shape and framing).

The protocol is intentionally runtime-agnostic: the same envelope can carry
a Python or Octave request, distinguished by the `runtime` field. Framing
uses a decimal byte length followed by a newline, then the JSON payload,
so newlines inside captured output do not corrupt frame boundaries.
"""

import io
import json

import pytest

from generic_grader.sandbox.protocol import (
    PROTOCOL_VERSION,
    Event,
    Request,
    Response,
    SandboxException,
    read_frame,
    read_request,
    read_response,
    write_frame,
    write_request,
    write_response,
)

# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def test_write_frame_round_trip_simple():
    buf = io.BytesIO()
    write_frame(buf, b'{"hello": "world"}')
    buf.seek(0)
    assert read_frame(buf) == b'{"hello": "world"}'


def test_write_frame_round_trip_with_newlines():
    """Payloads containing newlines must survive framing intact."""
    payload = b'{"events":[{"type":"stdout","data":"line one\\nline two\\n"}]}'
    buf = io.BytesIO()
    write_frame(buf, payload)
    buf.seek(0)
    assert read_frame(buf) == payload


def test_write_frame_round_trip_multiple_frames():
    buf = io.BytesIO()
    write_frame(buf, b"first")
    write_frame(buf, b"second\nwith\nnewlines")
    write_frame(buf, b"third")
    buf.seek(0)
    assert read_frame(buf) == b"first"
    assert read_frame(buf) == b"second\nwith\nnewlines"
    assert read_frame(buf) == b"third"


def test_read_frame_eof_returns_none():
    """An empty stream should signal EOF as None, not raise."""
    buf = io.BytesIO(b"")
    assert read_frame(buf) is None


def test_read_frame_rejects_non_decimal_length():
    buf = io.BytesIO(b"abc\n{}")
    with pytest.raises(SandboxException) as exc_info:
        read_frame(buf)
    assert "length" in str(exc_info.value).lower()


def test_read_frame_rejects_truncated_payload():
    """If the declared length exceeds what's available, that's a protocol error."""
    buf = io.BytesIO(b"100\n{}")
    with pytest.raises(SandboxException) as exc_info:
        read_frame(buf)
    assert "truncated" in str(exc_info.value).lower()


def test_read_frame_rejects_negative_length():
    buf = io.BytesIO(b"-5\nhello")
    with pytest.raises(SandboxException):
        read_frame(buf)


def test_read_frame_handles_empty_payload():
    """A zero-length frame is valid and yields an empty bytes object."""
    buf = io.BytesIO()
    write_frame(buf, b"")
    buf.seek(0)
    assert read_frame(buf) == b""


def test_write_frame_rejects_non_bytes_payload():
    """`write_frame` must refuse text-mode payloads to keep the wire stable."""
    with pytest.raises(TypeError):
        write_frame(io.BytesIO(), "not bytes")  # type: ignore[arg-type]


def test_write_frame_calls_flush_when_available():
    """Writers backed by a pipe rely on `flush` being invoked."""

    class _FlushTracker(io.BytesIO):
        flushed = False

        def flush(self):  # type: ignore[override]
            type(self).flushed = True
            super().flush()

    sink = _FlushTracker()
    write_frame(sink, b"ok")
    assert _FlushTracker.flushed is True


def test_write_frame_tolerates_stream_without_flush():
    """Some readers/writers (test fakes) omit `flush`; that must be OK."""

    class _NoFlush:
        def __init__(self):
            self.chunks = []

        def write(self, data):
            self.chunks.append(bytes(data))
            return len(data)

    sink = _NoFlush()
    write_frame(sink, b"hi")
    assert b"".join(sink.chunks) == b"2\nhi"


def test_read_frame_rejects_eof_mid_header():
    """A few digits followed by EOF (no terminator) is a protocol error."""
    buf = io.BytesIO(b"42")
    with pytest.raises(SandboxException) as exc_info:
        read_frame(buf)
    assert "truncated" in str(exc_info.value).lower()


def test_read_frame_rejects_overlong_header():
    """A length header longer than 20 digits cannot be a valid byte count."""
    buf = io.BytesIO(b"1" * 30 + b"\n")
    with pytest.raises(SandboxException) as exc_info:
        read_frame(buf)
    assert "length" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Request envelope
# ---------------------------------------------------------------------------


def test_request_minimal_fields():
    """A Request needs at least runtime + submission_dir + module + obj_name."""
    r = Request(
        runtime="python",
        submission_dir="/box/submission",
        module="submission",
        obj_name="main",
    )
    assert r.protocol_version == PROTOCOL_VERSION
    assert r.args == ()
    assert r.kwargs == {}
    assert r.entries == ()
    assert r.captures == ("stdout", "stderr", "return", "figures", "exception")


def test_request_to_json_round_trip():
    r = Request(
        runtime="python",
        submission_dir="/box/submission",
        module="submission",
        obj_name="compute_area",
        args=(3, 4),
        kwargs={"unit": "cm"},
        entries=("5\n",),
        time_limit_seconds=2,
        memory_limit_mb=512,
        log_limit=4096,
    )
    encoded = r.to_json()
    decoded = Request.from_json(encoded)
    assert decoded == r


def test_request_to_json_is_valid_json():
    r = Request(
        runtime="python",
        submission_dir="/box/submission",
        module="submission",
        obj_name="main",
    )
    payload = json.loads(r.to_json())
    assert payload["runtime"] == "python"
    assert payload["module"] == "submission"
    assert payload["protocol_version"] == PROTOCOL_VERSION


def test_request_from_json_rejects_wrong_protocol_version():
    bad = json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION + 99,
            "runtime": "python",
            "submission_dir": "/box/submission",
            "module": "submission",
            "obj_name": "main",
        }
    )
    with pytest.raises(SandboxException) as exc_info:
        Request.from_json(bad)
    assert "protocol_version" in str(exc_info.value)


def test_request_from_json_rejects_missing_required_field():
    bad = json.dumps({"protocol_version": PROTOCOL_VERSION, "runtime": "python"})
    with pytest.raises(SandboxException):
        Request.from_json(bad)


def test_request_write_read_round_trip():
    """`write_request` -> `read_request` should be lossless across a stream."""
    r = Request(
        runtime="python",
        submission_dir="/box/submission",
        module="m",
        obj_name="f",
        args=(1, 2),
    )
    buf = io.BytesIO()
    write_request(buf, r)
    buf.seek(0)
    assert read_request(buf) == r


def test_read_request_eof_returns_none():
    assert read_request(io.BytesIO(b"")) is None


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


def test_response_minimal_fields():
    resp = Response(events=[])
    assert resp.exception is None
    assert resp.elapsed_seconds == 0.0


def test_response_to_json_round_trip():
    resp = Response(
        events=[
            Event(type="stdout", data="Enter a number: "),
            Event(type="stdin", data="5\n"),
            Event(type="return", value=25),
        ],
        elapsed_seconds=0.012,
    )
    decoded = Response.from_json(resp.to_json())
    assert decoded == resp


def test_response_serializes_exception_chain():
    """Exception chains must round-trip with type/message/traceback per link."""
    resp = Response(
        events=[],
        exception=SandboxException.serialized_chain(
            [
                {
                    "type": "ValueError",
                    "message": "bad input",
                    "traceback": '  File "submission.py", line 3, in main\n    raise ValueError("bad input")\n',
                },
                {
                    "type": "RuntimeError",
                    "message": "wrapper",
                    "traceback": '  File "submission.py", line 6, in caller\n    main()\n',
                },
            ]
        ),
    )
    decoded = Response.from_json(resp.to_json())
    assert decoded == resp
    assert decoded.exception is not None
    assert len(decoded.exception) == 2
    assert decoded.exception[0]["type"] == "ValueError"


def test_response_write_read_round_trip():
    resp = Response(events=[Event(type="stdout", data="hi\n")], elapsed_seconds=0.5)
    buf = io.BytesIO()
    write_response(buf, resp)
    buf.seek(0)
    assert read_response(buf) == resp


def test_read_response_eof_returns_none():
    assert read_response(io.BytesIO(b"")) is None


def test_response_from_json_rejects_wrong_protocol_version():
    bad = json.dumps({"protocol_version": PROTOCOL_VERSION + 99, "events": []})
    with pytest.raises(SandboxException):
        Response.from_json(bad)


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


def test_event_to_dict_round_trip():
    e = Event(type="stdout", data="hello\n")
    assert Event.from_dict(e.to_dict()) == e


def test_event_preserves_arbitrary_payload_fields():
    """A figure event carries a `properties` dict; a return event carries `value`."""
    fig = Event(
        type="figure",
        properties={"title": "My plot", "lines": [{"xdata": [1, 2], "ydata": [3, 4]}]},
    )
    assert Event.from_dict(fig.to_dict()) == fig

    ret = Event(type="return", value={"answer": 42})
    assert Event.from_dict(ret.to_dict()) == ret


def test_event_attribute_access():
    """Payload fields are reachable via attribute access at call sites."""
    e = Event(type="stdout", data="hello\n")
    assert e.data == "hello\n"


def test_event_attribute_access_missing_raises():
    e = Event(type="stdout", data="hi")
    with pytest.raises(AttributeError):
        _ = e.nonexistent_field


def test_event_repr_contains_type_and_payload():
    e = Event(type="return", value=42)
    text = repr(e)
    assert "return" in text
    assert "42" in text


def test_event_repr_with_no_payload():
    """An Event without payload fields still has a readable repr."""
    e = Event(type="ping")
    text = repr(e)
    assert "ping" in text


def test_event_equality_against_non_event_returns_not_implemented():
    """`Event.__eq__` against an unrelated object falls back cleanly."""
    e = Event(type="stdout", data="hi")
    assert (e == "not an event") is False
    assert (e == 42) is False


def test_request_from_json_rejects_malformed_json():
    with pytest.raises(SandboxException) as exc_info:
        Request.from_json("{not valid json")
    assert "json" in str(exc_info.value).lower()


def test_response_from_json_rejects_malformed_json():
    with pytest.raises(SandboxException) as exc_info:
        Response.from_json("{not valid json")
    assert "json" in str(exc_info.value).lower()
