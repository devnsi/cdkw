"""Command composition — pure: (verb, config, regions, extra args) → list of cdk commands."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cdkw.config import EnvironmentConfig, ProjectConfig


@dataclass(frozen=True)
class CdkCommand:
    argv: list[str]
    region: str
    selector: str
    cwd: Path

    @property
    def display(self) -> str:
        """Copy-pasteable command line (double quotes work in both bash and PowerShell)."""
        return " ".join(_quote(token) for token in self.argv)


def _quote(token: str) -> str:
    if any(c in token for c in " *?"):
        return f'"{token}"'
    return token


def compose_commands(
    verb: str,
    env_name: str,
    env_config: EnvironmentConfig,
    regions: Sequence[str],
    project: ProjectConfig,
    extra_args: Sequence[str],
    app_dir: Path,
) -> list[CdkCommand]:
    """One `cdk <verb>` invocation per region, in the given order.

    The region reaches app.py via --context only (app.py also honors CDK_DEPLOY_REGION,
    but context wins, so the wrapper sets nothing else).
    """
    commands = []
    for region in regions:
        selector = project.stack_pattern.format(environment=env_name, region=region)
        argv = [
            "npx",
            "cdk",
            verb,
            selector,
            "--context",
            f"{project.env_context_key}={env_name}",
            "--context",
            f"region={region}",
        ]
        if env_config.profile:
            argv += ["--profile", env_config.profile]
        argv += list(extra_args)
        commands.append(CdkCommand(argv=argv, region=region, selector=selector, cwd=app_dir))
    return commands
