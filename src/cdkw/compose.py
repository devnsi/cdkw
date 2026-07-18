"""Command composition — pure: (verb, config, regions, extra args) → list of cdk commands."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cdkw.config import EnvironmentConfig, ProjectConfig
from cdkw.errors import CdkwError
from cdkw.resolve import region_short, region_shortcodes


@dataclass(frozen=True)
class Hook:
    """A user shell command with its CDKW_* context vars (merged over os.environ at run time)."""

    command: str
    cwd: Path
    env: dict[str, str]


@dataclass(frozen=True)
class CdkCommand:
    argv: list[str]
    region: str
    selectors: list[str]
    cwd: Path
    pre_hook: Hook | None = None
    post_hook: Hook | None = None

    @property
    def selector(self) -> str:
        return " ".join(self.selectors)

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
    root: Path | None = None,
    *,
    stacks: Sequence[str] = (),
) -> list[CdkCommand]:
    """One `cdk <verb>` invocation per region, in the given order.

    The region reaches app.py via --context only (app.py also honors CDK_DEPLOY_REGION,
    but context wins, so the wrapper sets nothing else). `stacks` narrows the selection:
    each name replaces the trailing `/`-segment of the formatted stack_pattern, becoming
    one positional selector per name on the same command. Configured hooks are attached
    per command, running from the project root. A regionless environment (empty `regions`
    map) composes exactly one command from stack_pattern_regionless with no region context;
    the `regions` argument is ignored then.
    """
    hook_cwd = root or app_dir

    def unit(selectors: list[str], region: str) -> CdkCommand:
        argv = [
            "npx",
            "cdk",
            verb,
            *selectors,
            "--context",
            f"{project.env_context_key}={env_name}",
        ]
        if region:
            argv += ["--context", f"region={region}"]
        if env_config.profile:
            argv += ["--profile", env_config.profile]
        argv += list(extra_args)
        hook_env = {
            "CDKW_VERB": verb,
            "CDKW_ENVIRONMENT": env_name,
            "CDKW_STAGE": env_config.stage,
            "CDKW_ACCOUNT": env_config.account,
            "CDKW_PROFILE": env_config.profile or "",
            "CDKW_REGION": region,
            "CDKW_REGION_SHORT": region_short(region) if region else "",
        }
        return CdkCommand(
            argv=argv,
            region=region,
            selectors=selectors,
            cwd=app_dir,
            pre_hook=_hook(project.hooks.pre, hook_cwd, hook_env),
            post_hook=_hook(project.hooks.post, hook_cwd, hook_env),
        )

    if not env_config.regions:
        base = project.stack_pattern_regionless.format(environment=env_name)
        return [unit(_selectors(base, project.stack_pattern_regionless, stacks), "")]

    uses_short = "{region_short}" in project.stack_pattern
    shorts = region_shortcodes(env_config.regions) if uses_short else {}
    commands = []
    for region in regions:
        base = project.stack_pattern.format(
            environment=env_name,
            region=region,
            region_short=shorts[region] if uses_short else "",
        )
        commands.append(unit(_selectors(base, project.stack_pattern, stacks), region))
    return commands


def _selectors(base: str, pattern: str, stacks: Sequence[str]) -> list[str]:
    if not stacks:
        return [base]
    prefix, sep, _ = base.rpartition("/")
    if not sep:
        raise CdkwError(
            f"--stack needs a '/<segment>' in stack_pattern to replace (got '{pattern}')"
        )
    return [f"{prefix}/{stack}" for stack in stacks]


def _hook(command: str | None, cwd: Path, env: dict[str, str]) -> Hook | None:
    return Hook(command=command, cwd=cwd, env=env) if command else None
