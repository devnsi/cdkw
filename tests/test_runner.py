"""Hook execution semantics — real subprocesses for hooks, cdk itself faked out."""

import sys
from pathlib import Path

import pytest

from cdkw import runner
from cdkw.compose import CdkCommand, Hook
from cdkw.ui import UI


@pytest.fixture
def ui() -> UI:
    return UI("deploy", plain=True, quiet=True)


@pytest.fixture(autouse=True)
def no_npx(monkeypatch):
    monkeypatch.setattr(runner, "_resolve_npx", lambda: "npx")


class FakeCdk:
    """Stands in for runner._run_one; records the extra_env each command received."""

    def __init__(self, exit_codes=(0,)):
        self.exit_codes = list(exit_codes)
        self.calls: list[dict[str, str] | None] = []

    def __call__(self, command, npx, ui, extra_env=None):
        self.calls.append(extra_env)
        return self.exit_codes.pop(0), 0.1


def hook_script(tmp_path: Path, name: str, body: str) -> Hook:
    """A Hook running a real python script through the platform shell."""
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return Hook(
        command=f'"{sys.executable}" {script}',
        cwd=tmp_path,
        env={"CDKW_REGION": "us-east-1", "OUT_FILE": str(tmp_path / "out.txt")},
    )


def command(region: str, pre: Hook | None = None, post: Hook | None = None) -> CdkCommand:
    return CdkCommand(
        argv=["npx", "cdk", "deploy", f"env-{region}/*"],
        region=region,
        selector=f"env-{region}/*",
        cwd=Path("."),
        pre_hook=pre,
        post_hook=post,
    )


def cdk_argv(verb: str, *extra: str) -> list[str]:
    return ["npx", "cdk", verb, "env-use1/*", *extra]


class TestInheritStdio:
    @pytest.mark.parametrize("verb", ["deploy", "destroy", "watch"])
    def test_interactive_verbs_inherit_on_tty(self, verb):
        assert runner._inherit_stdio(cdk_argv(verb), stdin_tty=True, stderr_tty=True)

    @pytest.mark.parametrize("verb", ["synth", "diff", "list"])
    def test_other_verbs_stay_piped(self, verb):
        assert not runner._inherit_stdio(cdk_argv(verb), stdin_tty=True, stderr_tty=True)

    def test_requires_stdin_tty(self):
        assert not runner._inherit_stdio(cdk_argv("deploy"), stdin_tty=False, stderr_tty=True)

    def test_requires_stderr_tty(self):
        assert not runner._inherit_stdio(cdk_argv("deploy"), stdin_tty=True, stderr_tty=False)

    @pytest.mark.parametrize(
        "extra",
        [("--require-approval", "never"), ("--require-approval=never",)],
        ids=["separate", "equals"],
    )
    def test_deploy_with_approval_never_stays_piped(self, extra):
        argv = cdk_argv("deploy", *extra)
        assert not runner._inherit_stdio(argv, stdin_tty=True, stderr_tty=True)

    def test_deploy_with_approval_broadening_inherits(self):
        argv = cdk_argv("deploy", "--require-approval", "broadening")
        assert runner._inherit_stdio(argv, stdin_tty=True, stderr_tty=True)

    def test_last_approval_flag_wins(self):
        argv = cdk_argv("deploy", "--require-approval=never", "--require-approval", "broadening")
        assert runner._inherit_stdio(argv, stdin_tty=True, stderr_tty=True)

    @pytest.mark.parametrize("flag", ["--force", "-f"])
    def test_destroy_with_force_stays_piped(self, flag):
        argv = cdk_argv("destroy", flag)
        assert not runner._inherit_stdio(argv, stdin_tty=True, stderr_tty=True)

    def test_watch_inherits_regardless_of_flags(self):
        argv = cdk_argv("watch", "--require-approval", "never")
        assert runner._inherit_stdio(argv, stdin_tty=True, stderr_tty=True)

    def test_run_one_hands_child_the_real_stdio(self, ui, monkeypatch, capfd):
        monkeypatch.setattr(runner, "_inherit_stdio", lambda *args, **kwargs: True)
        cmd = CdkCommand(
            argv=["npx", "-c", "import sys; print('owned'); sys.exit(5)"],
            region="us-east-1",
            selector="*",
            cwd=Path("."),
            pre_hook=None,
            post_hook=None,
        )
        exit_code, duration = runner._run_one(cmd, sys.executable, ui)
        assert exit_code == 5
        assert duration >= 0
        assert "owned" in capfd.readouterr().out


class TestPreHook:
    def test_failure_skips_cdk_and_stops_sequence(self, tmp_path, ui, monkeypatch):
        fake = FakeCdk()
        monkeypatch.setattr(runner, "_run_one", fake)
        pre = hook_script(tmp_path, "pre.py", "import sys; sys.exit(3)")
        results = runner.run_commands(
            [command("us-east-1", pre=pre), command("eu-central-1", pre=pre)], ui
        )
        assert fake.calls == []
        assert [r.status for r in results] == ["failed", "skipped"]
        assert results[0].exit_code == 3

    def test_env_file_injected_into_cdk_child(self, tmp_path, ui, monkeypatch):
        fake = FakeCdk()
        monkeypatch.setattr(runner, "_run_one", fake)
        pre = hook_script(
            tmp_path,
            "pre.py",
            "import os\n"
            "with open(os.environ['CDKW_ENV'], 'w') as f:\n"
            "    f.write('# comment\\n\\nFOO=bar\\nmalformed line\\nBAZ=a=b\\n')\n",
        )
        results = runner.run_commands([command("us-east-1", pre=pre)], ui)
        assert results[0].status == "succeeded"
        assert fake.calls == [{"FOO": "bar", "BAZ": "a=b"}]

    def test_hook_sees_context_env(self, tmp_path, ui, monkeypatch):
        monkeypatch.setattr(runner, "_run_one", FakeCdk())
        pre = hook_script(
            tmp_path,
            "pre.py",
            "import os\n"
            "with open(os.environ['OUT_FILE'], 'w') as f:\n"
            "    f.write(os.environ['CDKW_REGION'])\n",
        )
        runner.run_commands([command("us-east-1", pre=pre)], ui)
        assert (tmp_path / "out.txt").read_text() == "us-east-1"


class TestPostHook:
    def test_fires_on_cdk_failure_with_exit_code(self, tmp_path, ui, monkeypatch):
        monkeypatch.setattr(runner, "_run_one", FakeCdk(exit_codes=[7]))
        post = hook_script(
            tmp_path,
            "post.py",
            "import os\n"
            "with open(os.environ['OUT_FILE'], 'w') as f:\n"
            "    f.write(os.environ['CDKW_EXIT_CODE'])\n",
        )
        results = runner.run_commands([command("us-east-1", post=post)], ui)
        assert (tmp_path / "out.txt").read_text() == "7"
        assert results[0].status == "failed"
        assert results[0].exit_code == 7
        assert results[0].hook_warning is None

    def test_failing_post_hook_is_warning_only(self, tmp_path, ui, monkeypatch):
        monkeypatch.setattr(runner, "_run_one", FakeCdk())
        post = hook_script(tmp_path, "post.py", "import sys; sys.exit(2)")
        results = runner.run_commands([command("us-east-1", post=post)], ui)
        assert results[0].status == "succeeded"
        assert results[0].exit_code == 0
        assert results[0].hook_warning == "post hook exited 2"

    def test_not_run_for_skipped_units(self, tmp_path, ui, monkeypatch):
        monkeypatch.setattr(runner, "_run_one", FakeCdk(exit_codes=[1]))
        post = hook_script(
            tmp_path,
            "post.py",
            "import os\n"
            "with open(os.environ['OUT_FILE'], 'a') as f:\n"
            "    f.write('ran ')\n",
        )
        results = runner.run_commands(
            [command("us-east-1", post=post), command("eu-central-1", post=post)], ui
        )
        assert [r.status for r in results] == ["failed", "skipped"]
        assert (tmp_path / "out.txt").read_text() == "ran "
