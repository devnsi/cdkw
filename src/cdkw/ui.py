"""Terminal output: plan → progress → summary, npm-style.

All decoration goes to stderr; stdout carries only pass-through CDK output, so
`cdkw synth` / `cdkw diff` stay pipeable. Rich handles TTY detection; --plain and
NO_COLOR force plain output.
"""

import re
from dataclasses import dataclass

import sys
import time
from rich.console import Console

from cdkw.compose import CdkCommand
from cdkw.config import EnvironmentConfig

# Opportunistic parse of CloudFormation event lines in CDK's progress output; never required.
_CFN_EVENT = re.compile(
    r"(?P<status>[A-Z]+_(?:IN_PROGRESS|COMPLETE|FAILED)(?:_[A-Z_]+)?)\s*\|"
    r"[^|]*\|\s*(?P<resource>\S+)\s*$"
)


@dataclass
class RegionResult:
    region: str
    status: str  # "succeeded" | "failed" | "skipped"
    exit_code: int | None
    duration: float
    command: CdkCommand | None = None
    hook_warning: str | None = None


def _elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s"


class UI:
    def __init__(self, verb: str, *, plain: bool = False, quiet: bool = False) -> None:
        self.verb = verb
        self.quiet = quiet
        # soft_wrap: command echoes must never be hard-wrapped — they are copy-pasteable
        if plain:
            self.err = Console(
                stderr=True, force_terminal=False, no_color=True, highlight=False, soft_wrap=True
            )
        else:
            self.err = Console(stderr=True, highlight=False, soft_wrap=True)
        self.fancy = self.err.is_terminal and not plain
        encoding = (self.err.options.encoding or "").lower()
        if "utf" in encoding:
            self.sym = {"ok": "✔", "fail": "✖", "queued": "○", "primary": "★", "bar": "│"}
            self._spinner = "dots"
        else:
            self.sym = {"ok": "+", "fail": "x", "queued": "o", "primary": "*", "bar": "|"}
            self._spinner = "line"
        self._status = None
        self._region_start_time = 0.0

    # ── plan ────────────────────────────────────────────────────────────────

    def plan(
            self,
            env_name: str,
            provenance: str,
            env_config: EnvironmentConfig,
            commands: list[CdkCommand],
    ) -> None:
        if self.quiet:
            return
        primary = env_config.primary_region
        region_bits = []
        for name in env_config.regions:
            region_bits.append(f"{name} {self.sym['primary']}" if name == primary else name)
        regions_note = None
        if primary:
            order_hint = "deployed last" if self.verb == "destroy" else "deployed first"
            regions_note = f"({self.sym['primary']} primary, {order_hint})"

        # (label, value, dim annotation); widths computed so annotations line up
        rows = [
            ("environment", env_name, f"({provenance})"),
            ("stage", f"{env_config.stage} → {env_config.account}", None),
            ("regions", ", ".join(region_bits), regions_note),
        ]
        label_width = max(len(label) for label, _, _ in rows)
        value_width = max((len(value) for _, value, note in rows if note), default=0)

        self.err.print()
        for label, value, note in rows:
            line = f"  [bold]{label:<{label_width}}[/bold]  {value}"
            if note:
                line += f"{' ' * (value_width - len(value))}   [dim]{note}[/dim]"
            self.err.print(line)
        self.err.print()
        self.err.print(f"  [bold]plan[/bold]  {len(commands)} × cdk {self.verb}")
        for index, command in enumerate(commands, start=1):
            self.err.print(f"    {index}. [cyan]{command.region:<15}[/cyan] {command.selector}")
        self.err.print()

    # ── per-region progress ─────────────────────────────────────────────────

    def echo_command(self, command: CdkCommand) -> None:
        self.err.print(f"[bold]$ {command.display}[/bold]")

    def echo_hook(self, command: str, kind: str) -> None:
        self.err.print(f"[bold]$ {command}[/bold]  [dim]({kind} hook)[/dim]")

    def injected_env(self, pairs: dict[str, str]) -> None:
        """Env vars the pre hook injected into the cdk child — shown so runs stay reproducible."""
        for key, value in pairs.items():
            self.err.print(f"  [dim]env {key}={value}[/dim]")

    def warn(self, message: str) -> None:
        self.err.print(f"[yellow]warning:[/yellow] {message}")

    def region_start(self, region: str) -> None:
        self._region_start_time = time.monotonic()
        if self.fancy:
            self._status = self.err.status(
                f"[cyan]{region}[/cyan]  {self.verb}", spinner=self._spinner
            )
            self._status.start()

    def _update_status(self, region: str, tail: str) -> None:
        if self._status is None:
            return
        elapsed = _elapsed(time.monotonic() - self._region_start_time)
        text = f"[cyan]{region}[/cyan]  {self.verb}   {elapsed}"
        if tail:
            text += f"   [dim]{tail}[/dim]"
        self._status.update(text)

    def cdk_log(self, region: str, line: str) -> None:
        """A line of CDK stderr output: dimmed and prefixed (diff output bypasses this)."""
        match = _CFN_EVENT.search(line)
        if match:
            self._update_status(region, f"{match['status']}  {match['resource']}")
        else:
            self._update_status(region, "")
        if self.quiet:
            return
        self.err.print(f"  {region} {self.sym['bar']} {line.rstrip()}", markup=False, style="dim")

    def passthrough_out(self, line: str) -> None:
        sys.stdout.write(line)
        sys.stdout.flush()

    def passthrough_err(self, line: str) -> None:
        """Un-dimmed stderr pass-through — used for `diff`, whose output is the product."""
        sys.stderr.write(line)
        sys.stderr.flush()

    def region_done(self, region: str, ok: bool, exit_code: int, duration: float) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None
        if ok:
            self.err.print(
                f"  [green]{self.sym['ok']}[/green] {region:<15} {self.verb}   {_elapsed(duration)}"
            )
        else:
            self.err.print(
                f"  [red]{self.sym['fail']}[/red] {region:<15} {self.verb}   "
                f"{_elapsed(duration)}   [red]exit {exit_code}[/red]"
            )

    # ── summary ─────────────────────────────────────────────────────────────

    def summary(self, env_name: str, results: list[RegionResult]) -> None:
        clean = all(r.hook_warning is None for r in results)
        if len(results) <= 1 and clean and all(r.status == "succeeded" for r in results):
            return  # single successful region: the region_done line already says it all
        total = sum(r.duration for r in results)
        self.err.print()
        self.err.print(f"  [bold]── {self.verb} {env_name} ──────────────────────────[/bold]")
        for r in results:
            warning = f"   [yellow]{r.hook_warning}[/yellow]" if r.hook_warning else ""
            if r.status == "succeeded":
                self.err.print(
                    f"  [green]{self.sym['ok']}[/green] {r.region:<15} {_elapsed(r.duration)}{warning}"
                )
            elif r.status == "failed":
                self.err.print(
                    f"  [red]{self.sym['fail']}[/red] {r.region:<15} {_elapsed(r.duration)}   "
                    f"[red]exit {r.exit_code} — sequence stopped[/red]{warning}"
                )
            else:
                self.err.print(f"  [dim]{self.sym['queued']} {r.region:<15} skipped[/dim]")
        counts = {
            "succeeded": sum(1 for r in results if r.status == "succeeded"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
        }
        self.err.print()
        self.err.print(
            f"  {counts['succeeded']} succeeded · {counts['failed']} failed · "
            f"{counts['skipped']} skipped        {_elapsed(total)}"
        )
        failed = next((r for r in results if r.status == "failed"), None)
        if failed and failed.command:
            self.err.print()
            self.err.print("  [dim]rerun the failed region with:[/dim]")
            self.err.print(f"  [bold]$ {failed.command.display}[/bold]")
        self.err.print()

    def error(self, message: str) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None
        self.err.print(f"[red]error:[/red] {message}")
