"""Sandbox subsystem for running submitted code under `isolate`.

This package provides:

- `protocol`: language-agnostic request/response envelope and framing.
- `python_runtime`: Python-specific worker that imports the submitted
  module, calls a requested object, and captures structured events.
- `worker`: stdio entrypoint that reads a request, dispatches by
  `runtime`, and writes a response.
- `runner` (forthcoming): host-side helper that spawns the worker under
  `isolate` with the correct bind mounts and limits.

See issue #98 for the design rationale.
"""
