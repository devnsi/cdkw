"""Sequential execution of composed cdk commands with live, prefixed streaming."""

import shutil
import subprocess
import time
from threading import Thread

from cdkw.compose import CdkCommand
from cdkw.errors import CdkwError
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
        ui.echo_command(command)
        exit_code, duration = _run_one(command, npx, ui)
        ok = exit_code == 0
        ui.region_done(command.region, ok, exit_code, duration)
        results.append(
            RegionResult(
                command.region,
                "succeeded" if ok else "failed",
                exit_code,
                duration,
                command,
            )
        )
        failed = not ok
    return results


def _run_one(command: CdkCommand, npx: str, ui: UI) -> tuple[int, float]:
    argv = [npx, *command.argv[1:]]
    start = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            cwd=command.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise CdkwError(f"failed to start {command.display}: {exc}") from exc

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
