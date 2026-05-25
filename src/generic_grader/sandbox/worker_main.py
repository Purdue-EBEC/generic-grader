"""Entry point that runs inside the isolate sandbox.

`isolate` invokes ``python -m generic_grader.sandbox.worker_main``.
This module reads exactly one framed `Request` from stdin, runs it
through `python_runtime.run_request`, writes the framed `Response`
to stdout, then exits.

It deliberately performs no work outside that critical path so that:

* The sandbox subprocess starts as fast as possible (no eager
  matplotlib import; `python_runtime` itself imports lazily).
* If the worker dies for any reason, the host can still distinguish
  a malformed/missing frame from a worker crash by checking the
  return code and the empty / partial stdout.

This module also serves as the in-process entry point used by the
unit tests for the runner: tests spawn ``python -m
generic_grader.sandbox.worker_main`` directly (no `isolate` wrapper)
as a stand-in for the real sandboxed subprocess.
"""

from __future__ import annotations

import sys

from generic_grader.sandbox.protocol import (
    SandboxException,
    read_request,
    write_response,
)
from generic_grader.sandbox.python_runtime import run_request


def main(stdin=None, stdout=None) -> int:
    """Read one request, run it, write one response. Return process exit code.

    stdin/stdout default to the binary buffers of the real process
    streams so the framed protocol stays byte-exact. Tests can pass
    in BytesIO buffers to exercise this entry point in-process.
    """
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer

    from generic_grader.sandbox.protocol import Response

    def _protocol_error(message: str) -> Response:
        return Response(
            events=[],
            exception=[
                {
                    "type": "SandboxProtocolError",
                    "message": message,
                    "traceback": "",
                }
            ],
            elapsed_seconds=0.0,
        )

    try:
        request = read_request(stdin)
    except SandboxException as e:
        # If we can't even parse the frame, surface the failure to
        # the host as a structured exception on an otherwise-empty
        # response. The host treats this as a runner-level failure.
        write_response(stdout, _protocol_error(str(e)))
        return 2

    if request is None:
        # Clean EOF before any frame was sent.  Surface this as a
        # protocol error rather than letting `run_request(None)` crash
        # with an opaque ``AttributeError``.
        write_response(
            stdout,
            _protocol_error("No request frame received from host."),
        )
        return 2

    response = run_request(request)
    write_response(stdout, response)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised only as a real subprocess
    raise SystemExit(main())
