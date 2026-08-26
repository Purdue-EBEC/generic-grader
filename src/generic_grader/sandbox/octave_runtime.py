"""Octave runtime stub for forward compatibility.

Layer 3 was designed with a runtime selector (`Request.runtime`) so a
future commit can hook the same sandbox infrastructure up to GNU
Octave.  Issue #98 only delivers the Python runtime, but the protocol
already accepts a ``runtime`` string and the worker dispatcher needs
to know what to do when a host sends ``runtime="octave"``.

Rather than crash the worker with an opaque ``AttributeError`` when a
future host (or a misconfigured grader) requests Octave, we register
this stub.  It returns a well-formed :class:`Response` whose only
content is a structured ``RuntimeNotImplementedError`` exception, so
the host's existing error-classification path can surface a clean
message to the student or test author.

When the real Octave runtime lands, this module will be replaced by
the corresponding implementation; the dispatcher contract
(``run_request(request: Request) -> Response``) is intentionally the
same as the Python runtime's, so the swap will be a one-line change
in ``worker_main``.
"""

from __future__ import annotations

from generic_grader.sandbox.protocol import Request, Response


def run_request(request: Request) -> Response:
    """Return a structured error response for the not-yet-built Octave runtime.

    The host sees the same shape of response it would see for any
    other runtime-level failure: an empty event list and a non-empty
    ``exception`` chain.  The error type is deliberately specific so
    callers can distinguish "Octave isn't built yet" from a generic
    SandboxRunError.
    """
    return Response(
        events=[],
        exception=[
            {
                "type": "RuntimeNotImplementedError",
                "message": (
                    "The Octave runtime is not implemented yet "
                    "(see issue #98).  Use `runtime='python'` until the "
                    "Octave worker lands."
                ),
                "traceback": "",
            }
        ],
        elapsed_seconds=0.0,
    )


__all__ = ("run_request",)
