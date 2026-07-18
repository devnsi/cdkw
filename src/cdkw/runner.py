"""Sequential execution of composed cdk commands with live, prefixed streaming."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Thread

from cdkw.compose import CdkCommand, Hook
from cdkw.errors import CdkwError
from cdkw.resolve import INTERACTIVE_VERBS
from cdkw.ui import UI, RegionResult


def _resolve_npx() -> str:
    """Full path to npx (npx.cmd on Windows) — argv uses the literal 'npx' for display."""
    path = shutil.which("npx")
    if not path:
        raise CdkwError("npx not found on PATH — install Node.js/npm to run the CDK CLI")
    return path


def run_commands(commands: list[CdkCommand], ui: UI) -> list[RegionResult]:
    """Run each command in order; a failure stops the sequence (later regions may depend on
    the primary region's global resources). Success is keyed on the exit code only — jsii on
    Windows sometimes prints cosmetic ENOTEMPTY errors to stderr after a successful synth.
    """
    npx = _resolve_npx()
    results: list[RegionResult] = []
    failed = False
    for command in commands:
        if failed:
            results.append(RegionResult(command.region, "skipped", None, 0.0, command))
            continue
        start = time.monotonic()
        injected, pre_exit = _run_pre_hook(command, ui)
        if pre_exit != 0:
            duration = time.monotonic() - start
            ui.region_done(command.region, False, pre_exit, duration)
            results.append(RegionResult(command.region, "failed", pre_exit, duration, command))
            failed = True
            continue
        ui.injected_env(injected)
        ui.echo_command(command)
        exit_code, duration = _run_one(command, npx, ui, injected)
        ok = exit_code == 0
        ui.region_done(command.region, ok, exit_code, duration)
        warning = _run_post_hook(command, ui, exit_code)
        results.append(
            RegionResult(
                command.region,
                "succeeded" if ok else "failed",
                exit_code,
                duration,
                command,
                hook_warning=warning,
            )
        )
        failed = not ok
    return results


def _run_pre_hook(command: CdkCommand, ui: UI) -> tuple[dict[str, str], int]:
    """Run the pre hook; returns (env vars it wrote to CDKW_ENV, its exit code)."""
    if command.pre_hook is None:
        return {}, 0
    ui.echo_hook(command.pre_hook.command, "pre")
    fd, env_file = tempfile.mkstemp(prefix="cdkw-env-", suffix=".txt", text=True)
    os.close(fd)
    try:
        exit_code = _run_hook(command.pre_hook, ui, command.region, {"CDKW_ENV": env_file})
        if exit_code != 0:
            return {}, exit_code
        return _read_env_file(Path(env_file), ui), 0
    finally:
        try:
            os.unlink(env_file)
        except OSError:
            pass


def _run_post_hook(command: CdkCommand, ui: UI, cdk_exit: int) -> str | None:
    """Run the post hook (fires on cdk failure too, for compensating actions).

    A failing post hook is a warning, never a run failure — the cdk result stands.
    """
    if command.post_hook is None:
        return None
    ui.echo_hook(command.post_hook.command, "post")
    exit_code = _run_hook(command.post_hook, ui, command.region, {"CDKW_EXIT_CODE": str(cdk_exit)})
    if exit_code == 0:
        return None
    warning = f"post hook exited {exit_code}"
    ui.warn(f"{command.region}: {warning}")
    return warning


def _read_env_file(path: Path, ui: UI) -> dict[str, str]:
    """KEY=VALUE lines the pre hook wrote for the cdk child; blanks and # comments ignored."""
    injected: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            ui.warn(f"ignoring malformed CDKW_ENV line: {line!r}")
            continue
        injected[key.strip()] = value
    return injected


def _run_hook(hook: Hook, ui: UI, region: str, extra_env: dict[str, str]) -> int:
    """Run a hook through the platform shell, streaming its output like cdk's."""
    try:
        process = subprocess.Popen(
            hook.command,
            shell=True,
            cwd=hook.cwd,
            env={**os.environ, **hook.env, **extra_env},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise CdkwError(f"failed to start hook {hook.command!r}: {exc}") from exc
    _pump(process.stdout, lambda line: ui.cdk_log(region, line))
    process.wait()
    return process.returncode


def _inherit_stdio(argv: list[str], *, stdin_tty: bool, stderr_tty: bool) -> bool:
    """Interactive verbs on a real terminal get the parent's stdio so CDK's own
    approval / confirmation prompts work — behind pipes they stall invisibly.
    stdin must be a TTY to answer, stderr to see the prompt at all. Runs whose
    flags already suppress the prompt keep the piped, dimmed treatment."""
    verb = argv[2]
    if verb not in INTERACTIVE_VERBS or not (stdin_tty and stderr_tty):
        return False
    return not _prompts_suppressed(verb, argv)


def _prompts_suppressed(verb: str, argv: list[str]) -> bool:
    """Best-effort check that the run cannot prompt. Partial by design: cdk.json's
    requireApproval setting is invisible here, so those runs still inherit stdio
    (harmless — only the dimmed prefix is lost); watch owns the terminal regardless."""
    if verb == "deploy":
        return _flag_value(argv, "--require-approval") == "never"
    if verb == "destroy":
        return "--force" in argv or "-f" in argv
    return False


def _flag_value(argv: list[str], flag: str) -> str | None:
    """Last value of a `--flag value` / `--flag=value` pair (yargs: last one wins)."""
    value = None
    for i, token in enumerate(argv):
        if token == flag and i + 1 < len(argv):
            value = argv[i + 1]
        elif token.startswith(flag + "="):
            value = token.partition("=")[2]
    return value


def _run_one(
    command: CdkCommand, npx: str, ui: UI, extra_env: dict[str, str] | None = None
) -> tuple[int, float]:
    argv = [npx, *command.argv[1:]]
    env = None
    if extra_env:
        env = {**os.environ, **extra_env}
    if command.argv[2] == "diff" and ui.fancy and "NO_COLOR" not in os.environ:
        env = {**(env or os.environ), "FORCE_COLOR": "1"}
    inherit = _inherit_stdio(
        command.argv, stdin_tty=sys.stdin.isatty(), stderr_tty=sys.stderr.isatty()
    )
    popen_kwargs: dict = {"cwd": command.cwd, "env": env}
    if not inherit:
        popen_kwargs.update(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, **popen_kwargs)
    except OSError as exc:
        raise CdkwError(f"failed to start {command.display}: {exc}") from exc

    if inherit:
        ui.region_start(command.region, live=False)
        process.wait()
        return process.returncode, time.monotonic() - start

    # diff output goes to stderr and is the *product* of the command — pass it through
    # untouched; every other verb gets the dimmed, region-prefixed treatment.
    if command.argv[2] == "diff":
        on_stderr = ui.passthrough_err
    else:
        on_stderr = lambda line: ui.cdk_log(command.region, line)  # noqa: E731

    ui.region_start(command.region)
    threads = [
        Thread(target=_pump, args=(process.stdout, ui.passthrough_out), daemon=True),
        Thread(target=_pump, args=(process.stderr, on_stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    process.wait()
    return process.returncode, time.monotonic() - start


def _pump(stream, callback) -> None:
    with stream:
        for line in stream:
            callback(line)
