"""Tests for the unprivileged (sandboxed) student run in the Octave runtime.

The real privilege drop needs root, so ``Popen`` is mocked and the tests check
what the grader sets up: who the process runs as, what it can see, and what
the grader refuses to do.
"""

from __future__ import annotations

import os
import stat
import subprocess
from io import StringIO
from unittest.mock import patch

import pytest

from generic_grader.runtimes import octave as octave_mod
from generic_grader.runtimes import sandbox as sandbox_mod
from generic_grader.runtimes.base import RuntimeUnavailableError
from generic_grader.runtimes.octave import OctaveRuntime, OctaveRuntimeError
from generic_grader.runtimes.sandbox import Sandbox
from generic_grader.utils.options import Options

from . import test_octave

SHARED = Sandbox(uid=4242, gid=4343, dedicated=False)
DEDICATED = Sandbox(uid=4242, gid=4343, dedicated=True)


def _opts(**overrides):
    base = {
        "language": "octave",
        "obj_name": "main",
        "ref_module": "ref_main",
        "sub_module": "main",
        "weight": 1,
    }
    base.update(overrides)
    return Options(**base)


@pytest.fixture
def layout(fix_syspath, monkeypatch):
    """A grader directory (the cwd) and a separate submission directory."""
    (fix_syspath / "ref_main.m").write_text("disp('secret')\n")
    (fix_syspath / "ref_other.m").write_text("disp('other secret')\n")
    (fix_syspath / "tests").mkdir()
    (fix_syspath / "tests" / "test_config.py").write_text("answer = 42\n")
    (fix_syspath / "main.m").write_text("disp('student')\n")
    submitted = fix_syspath.parent / (fix_syspath.name + "_submission")
    submitted.mkdir()
    (submitted / "main.m").write_text("disp('student')\n")
    (submitted / "helper.m").write_text("function h()\nend\n")
    (submitted / "data.csv").write_text("1,2\n")
    monkeypatch.setenv(sandbox_mod.SUBMISSION_DIR_ENV, str(submitted))
    return SimpleLayout(fix_syspath, submitted)


class SimpleLayout:
    def __init__(self, grader, submitted):
        self.grader = grader
        self.submitted = submitted
        self.student = str(grader / "main.m")
        self.reference = str(grader / "ref_main.m")


@pytest.fixture
def sandboxed(monkeypatch):
    """Sandbox in effect, the ownership change stubbed, reference hidden."""
    state = {"sandbox": SHARED, "owned": []}
    monkeypatch.setattr(octave_mod, "resolve_sandbox", lambda: state["sandbox"])
    monkeypatch.setattr(octave_mod, "can_read", lambda *_: False)
    monkeypatch.setattr(
        OctaveRuntime,
        "_hand_over",
        staticmethod(lambda sandbox, stage: state["owned"].append(stage)),
    )
    return state


def _run(layout, handle=None, options=None, **proc):
    """Run with a mocked process; return the Popen call and what it saw."""
    helper = test_octave.TestRunMocked()
    stack, fake_proc, mock_popen = helper._mock_proc(**proc)
    seen = {}

    def popen(argv, **kwargs):
        stage = kwargs["cwd"]
        seen["stage"] = stage
        seen["files"] = sorted(os.listdir(stage))
        seen["env"] = kwargs["env"]
        return fake_proc

    mock_popen.side_effect = popen
    with stack:
        OctaveRuntime().run(
            options or _opts(),
            handle or layout.student,
            StringIO(),
            iter([]),
        )
    return mock_popen.call_args.kwargs, seen


class TestSandboxedStudentRun:
    def test_process_runs_as_the_sandbox_user_with_no_extra_groups(
        self, layout, sandboxed
    ):
        kwargs, _ = _run(layout)
        assert kwargs["user"] == 4242
        assert kwargs["group"] == 4343
        assert kwargs["extra_groups"] == []

    def test_sees_only_what_the_student_submitted(self, layout, sandboxed):
        _, seen = _run(layout)
        assert "main.m" in seen["files"]
        assert "helper.m" in seen["files"]
        assert "data.csv" in seen["files"]
        assert not any(name.startswith("ref_") for name in seen["files"])
        assert "tests" not in seen["files"]

    def test_runs_in_a_private_directory_not_the_grader_directory(
        self, layout, sandboxed
    ):
        kwargs, seen = _run(layout)
        assert seen["stage"] != str(layout.grader)
        assert not os.path.exists(seen["stage"])  # cleaned up afterwards
        assert sandboxed["owned"] == [seen["stage"]]
        assert kwargs["cwd"] == seen["stage"]

    def test_home_and_tmpdir_are_the_private_directory(self, layout, sandboxed):
        _, seen = _run(layout)
        assert seen["env"]["HOME"] == seen["stage"]
        assert seen["env"]["TMPDIR"] == seen["stage"]

    def test_the_grader_script_is_staged_from_the_handle(self, layout, sandboxed):
        """The student file comes from the handle, under the script's name."""
        (layout.submitted / "main.m").unlink()
        _, seen = _run(layout)
        assert "main.m" in seen["files"]

    def test_sidecars_are_created_inside_the_private_directory(self, layout, sandboxed):
        options = _opts(args=(1,))
        _, seen = _run(layout, options=options)
        assert any(n.startswith("gg_octave_return_") for n in seen["files"])
        assert any(n.startswith("gg_octave_plot_") for n in seen["files"])

    def test_function_mode_uses_the_private_directory_too(self, layout, sandboxed):
        options = _opts(args=(1,))
        kwargs, seen = _run(layout, options=options)
        assert kwargs["cwd"] == seen["stage"]
        assert "main.m" in seen["files"]
        assert "helper.m" in seen["files"]

    def test_symlinks_in_the_submission_are_not_followed(self, layout, sandboxed):
        os.symlink(layout.reference, layout.submitted / "leak.m")
        os.symlink(layout.grader / "tests", layout.submitted / "leakdir")
        _, seen = _run(layout)
        assert "leak.m" not in seen["files"]
        assert "leakdir" not in seen["files"]

    def test_subdirectories_are_copied_but_their_symlinks_are_kept_as_links(
        self, layout, sandboxed
    ):
        sub = layout.submitted / "lib"
        sub.mkdir()
        (sub / "util.m").write_text("function u()\nend\n")
        os.symlink(layout.reference, sub / "leak.m")
        helper = test_octave.TestRunMocked()
        stack, fake_proc, mock_popen = helper._mock_proc()
        seen = {}

        def popen(argv, **kwargs):
            stage = kwargs["cwd"]
            seen["util"] = os.path.isfile(os.path.join(stage, "lib", "util.m"))
            seen["link"] = os.path.islink(os.path.join(stage, "lib", "leak.m"))
            return fake_proc

        mock_popen.side_effect = popen
        with stack:
            OctaveRuntime().run(_opts(), layout.student, StringIO(), iter([]))
        assert seen == {"util": True, "link": True}

    def test_provided_files_are_copied_from_the_grader_directory(
        self, layout, sandboxed
    ):
        (layout.grader / "Sucrose_Data.csv").write_text("0,1\n")
        (layout.grader / "images").mkdir()
        (layout.grader / "images" / "a.png").write_text("png")
        options = _opts(provided_files=("Sucrose_*.csv", "images"))
        _, seen = _run(layout, options=options)
        assert "Sucrose_Data.csv" in seen["files"]
        assert "images" in seen["files"]

    def test_files_named_after_the_sides_are_not_copied_twice(self, layout, sandboxed):
        (layout.submitted / "ref_main.m").write_text("disp('forged')\n")
        _, seen = _run(layout)
        assert "ref_main.m" not in seen["files"]

    def test_unrelated_reference_files_are_never_staged(self, layout, sandboxed):
        _, seen = _run(layout)
        assert "ref_other.m" not in seen["files"]


class TestTrustedReferenceRun:
    def test_reference_runs_as_the_grader_in_place(self, layout, sandboxed):
        kwargs, seen = _run(layout, handle=layout.reference)
        assert "user" not in kwargs
        assert "group" not in kwargs
        assert "extra_groups" not in kwargs
        assert kwargs["cwd"] == str(layout.grader)
        assert sandboxed["owned"] == []
        assert seen["env"]["HOME"] != seen["stage"]

    def test_a_module_that_is_both_sides_is_treated_as_student_code(
        self, layout, sandboxed
    ):
        options = _opts(ref_module="main", sub_module="main")
        kwargs, _ = _run(layout, options=options)
        assert kwargs["user"] == 4242

    def test_does_not_even_look_up_a_sandbox_for_the_reference(
        self, layout, sandboxed, monkeypatch
    ):
        def boom():
            raise AssertionError("looked up")  # pragma: no cover

        monkeypatch.setattr(octave_mod, "resolve_sandbox", boom)
        kwargs, _ = _run(layout, handle=layout.reference)
        assert "user" not in kwargs


class TestFailClosed:
    def test_missing_submission_dir(self, layout, sandboxed, monkeypatch):
        monkeypatch.delenv(sandbox_mod.SUBMISSION_DIR_ENV)
        with pytest.raises(RuntimeUnavailableError, match="SUBMISSION_DIR"):
            _run(layout)

    def test_reference_readable_by_the_sandbox_user(
        self, layout, sandboxed, monkeypatch
    ):
        monkeypatch.setattr(octave_mod, "can_read", lambda *_: True)
        with pytest.raises(RuntimeUnavailableError, match="can read the reference"):
            _run(layout)

    def test_reference_check_is_made_against_the_reference_file(
        self, layout, sandboxed, monkeypatch
    ):
        checked = []
        monkeypatch.setattr(
            octave_mod, "can_read", lambda sb, path: checked.append((sb, path)) or False
        )
        _run(layout)
        assert checked == [(SHARED, layout.reference)]

    def test_no_reference_file_nothing_to_hide(self, layout, sandboxed, monkeypatch):
        os.unlink(layout.reference)
        monkeypatch.setattr(octave_mod, "can_read", lambda *_: True)
        _run(layout)

    def test_cannot_switch_user(self, layout, sandboxed):
        helper = test_octave.TestRunMocked()
        stack, _, mock_popen = helper._mock_proc()
        mock_popen.side_effect = PermissionError(1, "Operation not permitted")
        with stack, pytest.raises(RuntimeUnavailableError, match="uid 4242"):
            OctaveRuntime().run(_opts(), layout.student, StringIO(), iter([]))

    def test_staging_is_removed_when_the_run_fails(self, layout, sandboxed):
        helper = test_octave.TestRunMocked()
        stack, _, mock_popen = helper._mock_proc()
        stages = []

        def popen(argv, **kwargs):
            stages.append(kwargs["cwd"])
            raise PermissionError(1, "no")

        mock_popen.side_effect = popen
        with stack, pytest.raises(RuntimeUnavailableError):
            OctaveRuntime().run(_opts(), layout.student, StringIO(), iter([]))
        assert not os.path.exists(stages[0])


class TestSweep:
    def test_dedicated_user_loses_every_process_after_the_run(self, layout, sandboxed):
        sandboxed["sandbox"] = DEDICATED
        with patch.object(octave_mod, "kill_all_processes") as sweep:
            _run(layout)
        sweep.assert_called_once_with(DEDICATED)

    def test_shared_user_is_never_swept(self, layout, sandboxed):
        with patch.object(octave_mod, "kill_all_processes") as sweep:
            _run(layout)
        sweep.assert_not_called()

    def test_sweep_also_runs_after_a_timeout(self, layout, sandboxed):
        sandboxed["sandbox"] = DEDICATED
        helper = test_octave.TestRunMocked()
        stack, fake_proc, _ = helper._mock_proc()
        fake_proc.communicate.side_effect = subprocess.TimeoutExpired("octave", 1)
        with (
            stack,
            patch.object(octave_mod, "kill_all_processes") as sweep,
            pytest.raises(octave_mod.OctaveTimeoutError),
        ):
            OctaveRuntime().run(_opts(), layout.student, StringIO(), iter([]))
        sweep.assert_called_once_with(DEDICATED)


class TestHandOver:
    def test_directory_is_private_and_everything_inside_is_chowned(self, tmp_path):
        stage = tmp_path / "stage"
        (stage / "sub").mkdir(parents=True)
        (stage / "sub" / "f.m").write_text("x")
        (stage / "link").symlink_to("/etc/hostname")
        stage.chmod(0o755)
        me = Sandbox(uid=os.getuid(), gid=os.getgid(), dedicated=True)
        with patch.object(octave_mod.os, "lchown") as lchown:
            OctaveRuntime._hand_over(me, str(stage))
        assert stat.S_IMODE(stage.stat().st_mode) == 0o700
        owned = {call.args[0] for call in lchown.call_args_list}
        assert owned == {
            str(stage),
            str(stage / "sub"),
            str(stage / "sub" / "f.m"),
            str(stage / "link"),
        }
        assert all(call.args[1:] == (me.uid, me.gid) for call in lchown.call_args_list)

    def test_a_real_chown_to_ourselves_works(self, tmp_path):
        stage = tmp_path / "stage"
        stage.mkdir()
        (stage / "f.m").write_text("x")
        me = Sandbox(uid=os.getuid(), gid=os.getgid(), dedicated=True)
        OctaveRuntime._hand_over(me, str(stage))
        assert stage.stat().st_uid == me.uid


class TestSidecarsWrittenByStudentCode:
    """The grader reads these as a privileged user from a directory the student
    controls, so a swapped-in symlink or FIFO must not be followed or block."""

    def test_symlinked_plot_sidecar_is_ignored(self, tmp_path):
        secret = tmp_path / "secret.json"
        secret.write_text('{"figures": []}')
        link = tmp_path / "plot.json"
        link.symlink_to(secret)
        assert OctaveRuntime._read_plot_sidecar(str(link)) is None

    def test_symlinked_return_sidecar_is_an_error_not_a_leak(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP SECRET")
        link = tmp_path / "return.json"
        link.symlink_to(secret)
        with pytest.raises(OctaveRuntimeError) as err:
            OctaveRuntime._read_sidecar(str(link))
        assert "TOP SECRET" not in str(err.value)
        assert "TOP SECRET" not in err.value.stderr

    def test_fifo_sidecar_does_not_block(self, tmp_path):
        fifo = tmp_path / "return.json"
        os.mkfifo(fifo)
        with pytest.raises(OctaveRuntimeError):
            OctaveRuntime._read_sidecar(str(fifo))
        assert OctaveRuntime._read_plot_sidecar(str(fifo)) is None

    def test_invalid_utf8_is_decoded_leniently(self, tmp_path):
        path = tmp_path / "return.json"
        path.write_bytes(b"\xff\xfe")
        with pytest.raises(OctaveRuntimeError, match="decode"):
            OctaveRuntime._read_sidecar(str(path))
