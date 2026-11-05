"""Tests for :mod:`generic_grader.runtimes.sandbox`.

Nothing here may signal real processes: every ``kill`` is mocked or exits
before it runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from generic_grader.runtimes import sandbox
from generic_grader.runtimes.base import RuntimeUnavailableError
from generic_grader.runtimes.sandbox import (
    _KILL_ALL,
    Sandbox,
    can_read,
    kill_all_processes,
    resolve_sandbox,
    submission_dir,
)


def _entry(name="nobody", uid=65534, gid=65534):
    return SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid)


@pytest.fixture
def as_root():
    with patch.object(sandbox.os, "geteuid", return_value=0):
        yield


class TestResolveSandbox:
    def test_none_disables_even_as_root(self, monkeypatch, as_root):
        monkeypatch.setenv(sandbox.SANDBOX_USER_ENV, "none")
        assert resolve_sandbox() is None

    def test_unset_does_nothing_when_not_root(self, monkeypatch):
        monkeypatch.delenv(sandbox.SANDBOX_USER_ENV)
        with patch.object(sandbox.os, "geteuid", return_value=1000):
            assert resolve_sandbox() is None

    def test_explicit_user_needs_root(self, monkeypatch):
        monkeypatch.setenv(sandbox.SANDBOX_USER_ENV, "grader")
        with (
            patch.object(sandbox.os, "geteuid", return_value=1000),
            pytest.raises(RuntimeUnavailableError, match="as root"),
        ):
            resolve_sandbox()

    def test_root_defaults_to_shared_nobody(self, monkeypatch, as_root):
        monkeypatch.delenv(sandbox.SANDBOX_USER_ENV)
        with patch.object(sandbox.pwd, "getpwnam", return_value=_entry()) as lookup:
            result = resolve_sandbox()
        lookup.assert_called_once_with("nobody")
        assert result == Sandbox(uid=65534, gid=65534, dedicated=False)

    def test_named_user_is_dedicated(self, monkeypatch, as_root):
        monkeypatch.setenv(sandbox.SANDBOX_USER_ENV, "grader")
        entry = _entry("grader", 1500, 1501)
        with patch.object(sandbox.pwd, "getpwnam", return_value=entry):
            assert resolve_sandbox() == Sandbox(uid=1500, gid=1501, dedicated=True)

    def test_numeric_user_is_looked_up_by_uid(self, monkeypatch, as_root):
        monkeypatch.setenv(sandbox.SANDBOX_USER_ENV, "1500")
        entry = _entry("grader", 1500, 1501)
        with patch.object(sandbox.pwd, "getpwuid", return_value=entry) as lookup:
            assert resolve_sandbox().uid == 1500
        lookup.assert_called_once_with(1500)

    def test_explicit_nobody_is_not_dedicated(self, monkeypatch, as_root):
        monkeypatch.setenv(sandbox.SANDBOX_USER_ENV, "nobody")
        with patch.object(sandbox.pwd, "getpwnam", return_value=_entry()):
            assert resolve_sandbox().dedicated is False

    def test_unknown_user_fails_closed(self, monkeypatch, as_root):
        monkeypatch.setenv(sandbox.SANDBOX_USER_ENV, "ghost")
        with (
            patch.object(sandbox.pwd, "getpwnam", side_effect=KeyError("ghost")),
            pytest.raises(RuntimeUnavailableError, match="ghost"),
        ):
            resolve_sandbox()

    @pytest.mark.parametrize(
        "entry",
        [_entry("root", 0, 0), _entry("odd", 5, 0), _entry("odd", 0, 5)],
    )
    def test_root_identity_rejected(self, monkeypatch, as_root, entry):
        monkeypatch.setenv(sandbox.SANDBOX_USER_ENV, "whoever")
        with (
            patch.object(sandbox.pwd, "getpwnam", return_value=entry),
            pytest.raises(RuntimeUnavailableError, match="not be root"),
        ):
            resolve_sandbox()


class TestSubmissionDir:
    def test_unset_fails_closed(self, monkeypatch):
        monkeypatch.delenv(sandbox.SUBMISSION_DIR_ENV, raising=False)
        with pytest.raises(RuntimeUnavailableError, match=sandbox.SUBMISSION_DIR_ENV):
            submission_dir()

    def test_returns_configured_path(self, monkeypatch):
        monkeypatch.setenv(sandbox.SUBMISSION_DIR_ENV, "/autograder/submission")
        assert submission_dir() == "/autograder/submission"


class TestCanRead:
    """Mode bits are checked from the file's owner's point of view, because
    pytest's own tmp dirs are private and would hide every file from others."""

    @pytest.fixture
    def owner(self):
        return Sandbox(uid=os.getuid(), gid=os.getgid(), dedicated=True)

    def test_readable_file(self, tmp_path, owner):
        path = tmp_path / "f"
        path.write_text("x")
        assert can_read(owner, str(path))

    def test_unreadable_file(self, tmp_path, owner):
        path = tmp_path / "f"
        path.write_text("x")
        path.chmod(0o000)
        assert not can_read(owner, str(path))

    def test_directory_without_search_permission_hides_file(self, tmp_path, owner):
        (tmp_path / "d").mkdir()
        path = tmp_path / "d" / "f"
        path.write_text("x")
        (tmp_path / "d").chmod(0o600)
        try:
            assert not can_read(owner, str(path))
        finally:
            (tmp_path / "d").chmod(0o700)

    def test_other_users_get_the_other_bits(self, tmp_path):
        stranger = Sandbox(uid=os.getuid() + 1, gid=os.getgid() + 1, dedicated=True)
        assert can_read(stranger, "/usr/bin/env")
        path = tmp_path / "f"
        path.write_text("x")
        assert not can_read(stranger, str(path))  # tmp_path's parents are 0700

    def test_group_bits_apply_to_the_sandbox_group(self, tmp_path):
        path = tmp_path / "f"
        path.write_text("x")
        path.chmod(0o040)
        member = Sandbox(uid=os.getuid() + 1, gid=os.getgid(), dedicated=True)
        # Only the file's own bits are in question; ancestors are private.
        with patch.object(sandbox.Path, "parents", ()):
            assert can_read(member, str(path))

    def test_follows_symlinks_to_the_real_file(self, tmp_path, owner):
        real = tmp_path / "real"
        real.write_text("x")
        real.chmod(0o000)
        link = tmp_path / "link"
        link.symlink_to(real)
        assert not can_read(owner, str(link))


class TestKillAllProcesses:
    def test_refuses_a_shared_user(self):
        with (
            patch.object(sandbox.subprocess, "run") as run,
            pytest.raises(ValueError, match="shared"),
        ):
            kill_all_processes(Sandbox(uid=65534, gid=65534, dedicated=False))
        run.assert_not_called()

    def test_runs_the_helper_as_the_sandbox_user(self):
        with patch.object(sandbox.subprocess, "run") as run:
            kill_all_processes(Sandbox(uid=1500, gid=1501, dedicated=True))
        argv = run.call_args.args[0]
        assert argv[:3] == [sys.executable, "-I", "-c"]
        assert argv[3:] == [_KILL_ALL, "1500"]
        kwargs = run.call_args.kwargs
        assert (kwargs["user"], kwargs["group"]) == (1500, 1501)
        assert kwargs["extra_groups"] == []

    @pytest.mark.parametrize("uid", ["0", str(os.getuid() + 1)])
    def test_helper_exits_before_killing_if_the_uid_did_not_change(self, uid):
        """Run for real, as the current non-root user, with a uid we are not:
        it must refuse rather than reach ``os.kill``."""
        result = subprocess.run(
            [sys.executable, "-I", "-c", _KILL_ALL, uid],
            check=False,
            timeout=10,
        )
        assert result.returncode == 2
