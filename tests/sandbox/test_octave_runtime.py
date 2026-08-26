"""Tests for the Octave runtime stub.

The stub returns a structured error response so the host can surface
"Octave isn't built yet" without crashing the worker.
"""

from __future__ import annotations

import pytest

from generic_grader.sandbox.octave_runtime import run_request
from generic_grader.sandbox.protocol import Request


def _make_request() -> Request:
    return Request(
        runtime="octave",
        submission_dir="/tmp",
        module="m",
        obj_name="f",
    )


def test_octave_run_request_returns_response():
    response = run_request(_make_request())
    assert response.events == []
    assert response.exception is not None
    assert len(response.exception) == 1


def test_octave_run_request_exception_type_is_runtime_not_implemented():
    response = run_request(_make_request())
    assert response.exception[0]["type"] == "RuntimeNotImplementedError"


def test_octave_run_request_message_mentions_issue_and_alternative():
    response = run_request(_make_request())
    msg = response.exception[0]["message"]
    assert "Octave" in msg
    assert "not implemented" in msg
    assert "python" in msg


def test_octave_run_request_traceback_is_empty():
    response = run_request(_make_request())
    assert response.exception[0]["traceback"] == ""


def test_octave_run_request_elapsed_time_is_zero():
    """A stub returns instantly; the timer reflects that."""
    response = run_request(_make_request())
    assert response.elapsed_seconds == 0.0


def test_octave_run_request_roundtrips_through_protocol_json():
    """Stub response is JSON-serializable like every other response."""
    import json

    response = run_request(_make_request())
    payload = json.loads(response.to_json())
    assert payload["exception"][0]["type"] == "RuntimeNotImplementedError"


@pytest.mark.parametrize(
    "obj_name",
    ["main", "process_data", "with_underscores"],
)
def test_octave_run_request_ignores_request_fields(obj_name):
    """The stub returns the same error regardless of request contents."""
    request = Request(
        runtime="octave",
        submission_dir="/anywhere",
        module="ignored",
        obj_name=obj_name,
    )
    response = run_request(request)
    assert response.exception[0]["type"] == "RuntimeNotImplementedError"
