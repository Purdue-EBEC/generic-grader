"""Tests for the worker_main entry point and its runtime dispatcher.

These tests exercise the ``worker_main.main`` entry point in-process
via ``BytesIO`` buffers, plus the ``_dispatch_request`` helper that
chooses a runtime based on ``Request.runtime``.
"""

from __future__ import annotations

import io
import json

from generic_grader.sandbox import worker_main
from generic_grader.sandbox.protocol import Request, Response, write_request


def _write_request_bytes(request: Request) -> bytes:
    buf = io.BytesIO()
    write_request(buf, request)
    return buf.getvalue()


def _read_response_bytes(buf: bytes) -> dict:
    # Same length-prefixed framing as `read_response`, but we don't
    # want to depend on Response.from_dict semantics here -- the test
    # asserts on the raw JSON shape.
    newline = buf.index(b"\n")
    length = int(buf[:newline])
    payload = buf[newline + 1 : newline + 1 + length]
    return json.loads(payload)


# ---------------------------------------------------------------------------
# Runtime dispatch
# ---------------------------------------------------------------------------


def test_dispatch_python_runtime_routes_to_python_run_request(monkeypatch):
    """A python request goes to ``python_runtime.run_request``."""
    request = Request(runtime="python", submission_dir="/tmp", module="m", obj_name="f")
    sentinel = Response(events=[], exception=None, elapsed_seconds=1.5)
    captured = {}

    def _fake_python_run(req):
        captured["request"] = req
        return sentinel

    monkeypatch.setattr(
        "generic_grader.sandbox.python_runtime.run_request", _fake_python_run
    )
    out = worker_main._dispatch_request(request)
    assert out is sentinel
    assert captured["request"] is request


def test_dispatch_octave_runtime_routes_to_octave_run_request(monkeypatch):
    """An octave request goes to the Octave stub's ``run_request``."""
    request = Request(runtime="octave", submission_dir="/tmp", module="m", obj_name="f")
    sentinel = Response(events=[], exception=None, elapsed_seconds=2.5)
    captured = {}

    def _fake_octave_run(req):
        captured["request"] = req
        return sentinel

    monkeypatch.setattr(
        "generic_grader.sandbox.octave_runtime.run_request", _fake_octave_run
    )
    out = worker_main._dispatch_request(request)
    assert out is sentinel
    assert captured["request"] is request


def test_dispatch_unknown_runtime_returns_structured_error():
    request = Request(runtime="erlang", submission_dir="/tmp", module="m", obj_name="f")
    response = worker_main._dispatch_request(request)
    assert response.events == []
    assert response.exception is not None
    assert response.exception[0]["type"] == "UnknownRuntimeError"
    assert "erlang" in response.exception[0]["message"]


def test_dispatch_runtime_is_case_insensitive():
    """``runtime='PYTHON'`` should still route to the Python worker."""
    request = Request(runtime="PYTHON", submission_dir="/tmp", module="m", obj_name="f")

    # The real python worker would need module resolution; we just
    # confirm the dispatcher doesn't fall through to the error branch.
    # The simplest signal: the exception (if any) is not the dispatch
    # error -- it's whatever python_runtime produces (probably a
    # ModuleNotFoundError for our fake module).
    response = worker_main._dispatch_request(request)
    if response.exception:
        assert response.exception[0]["type"] != "UnknownRuntimeError"


def test_dispatch_empty_runtime_string_is_treated_as_unknown():
    request = Request(runtime="", submission_dir="/tmp", module="m", obj_name="f")
    response = worker_main._dispatch_request(request)
    assert response.exception is not None
    assert response.exception[0]["type"] == "UnknownRuntimeError"


# ---------------------------------------------------------------------------
# main(): framed I/O
# ---------------------------------------------------------------------------


def test_main_round_trips_a_python_request(monkeypatch):
    """A valid request -> response, exit code 0."""
    request = Request(runtime="python", submission_dir="/tmp", module="m", obj_name="f")
    sentinel = Response(events=[], exception=None, elapsed_seconds=0.25)

    def _fake_python_run(req):
        return sentinel

    monkeypatch.setattr(
        "generic_grader.sandbox.python_runtime.run_request", _fake_python_run
    )

    stdin = io.BytesIO(_write_request_bytes(request))
    stdout = io.BytesIO()
    code = worker_main.main(stdin=stdin, stdout=stdout)
    assert code == 0
    payload = _read_response_bytes(stdout.getvalue())
    assert payload["elapsed_seconds"] == 0.25
    assert payload["events"] == []


def test_main_returns_protocol_error_on_eof_before_frame():
    """Empty stdin -> structured 'no request' error and exit code 2."""
    stdin = io.BytesIO(b"")
    stdout = io.BytesIO()
    code = worker_main.main(stdin=stdin, stdout=stdout)
    assert code == 2
    payload = _read_response_bytes(stdout.getvalue())
    assert payload["exception"][0]["type"] == "SandboxProtocolError"
    assert "No request frame" in payload["exception"][0]["message"]


def test_main_returns_protocol_error_on_malformed_frame():
    """Garbage stdin -> structured protocol error and exit code 2."""
    stdin = io.BytesIO(b"this is not a valid frame")
    stdout = io.BytesIO()
    code = worker_main.main(stdin=stdin, stdout=stdout)
    assert code == 2
    payload = _read_response_bytes(stdout.getvalue())
    assert payload["exception"][0]["type"] == "SandboxProtocolError"


def test_main_dispatches_unknown_runtime_via_dispatcher():
    """An unknown runtime still produces exit code 0 (framed response wins)."""
    request = Request(runtime="cobol", submission_dir="/tmp", module="m", obj_name="f")
    stdin = io.BytesIO(_write_request_bytes(request))
    stdout = io.BytesIO()
    code = worker_main.main(stdin=stdin, stdout=stdout)
    assert code == 0
    payload = _read_response_bytes(stdout.getvalue())
    assert payload["exception"][0]["type"] == "UnknownRuntimeError"
