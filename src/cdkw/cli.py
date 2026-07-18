"""cdkw CLI — verbs 1:1 with cdk; everything after `--` passes through untouched."""

import sys
from typing import Annotated, Optional

import typer

from cdkw import __version__
from cdkw.compose import compose_commands
from cdkw.config import (
    EnvironmentConfig,
    find_project_root,
    known_environments,
    load_environment,
    load_project_config,
)
from cdkw.errors import CdkwError
from cdkw.resolve import (
    SINGLE_REGION_VERBS,
    current_git_branch,
    default_region_order,
    order_regions,
    resolve_environment,
)
from cdkw.runner import run_commands
from cdkw.ui import UI

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Thin CDK wrapper for multi-stage, multi-environment, multi-region deployments. "
    "Every run composes visible `cdk` commands, one per (environment, region).",
)

VERB_HELP = {
    "synth": "Synthesize templates for the environment's regions.",
    "diff": "Diff deployed stacks against the synthesized state.",
    "deploy": "Deploy one region at a time (explicit --region, --all-regions, or interactive pick).",
    "destroy": "Destroy one region at a time; --all-regions runs in reverse order, primary last.",
    "watch": "Watch for changes and hot-deploy a single region (runs until interrupted).",
    "list": "List the stacks per region.",
}


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cdkw {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Print version."),
    ] = False,
) -> None:
    pass


def _register(verb: str) -> None:
    @app.command(
        name=verb,
        help=VERB_HELP[verb] + " Args after `--` pass through to cdk untouched.",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )
    def command(
        ctx: typer.Context,
        environment: Annotated[
            Optional[str],
            typer.Argument(
                help="Environment name (e.g. test-main, feature-123); derived from the git branch when omitted."
            ),
        ] = None,
        region: Annotated[
            Optional[list[str]],
            typer.Option("--region", "-r", help="Target region(s), run in the given order."),
        ] = None,
        all_regions: Annotated[
            bool,
            typer.Option("--all-regions", help="All configured regions, primary first (destroy: primary last)."),
        ] = False,
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Print the composed cdk commands without executing.")
        ] = False,
        quiet: Annotated[
            bool, typer.Option("--quiet", help="Suppress plan block and dimmed CDK output.")
        ] = False,
        plain: Annotated[
            bool, typer.Option("--plain", help="Force plain output (no colors, spinners, prompts).")
        ] = False,
    ) -> None:
        code = _run_verb(verb, list(ctx.args), environment, list(region or []), all_regions, dry_run, quiet, plain)
        raise typer.Exit(code)


for _verb in VERB_HELP:
    _register(_verb)


def _run_verb(
    verb: str,
    extra_args: list[str],
    environment: str | None,
    requested_regions: list[str],
    all_regions: bool,
    dry_run: bool,
    quiet: bool,
    plain: bool,
) -> int:
    ui = UI(verb, plain=plain, quiet=quiet)
    try:
        # `cdkw deploy -- --require-approval never` lands the first passthrough token in
        # the positional slot; environment names never start with a dash.
        if environment and environment.startswith("-"):
            extra_args = [environment, *extra_args]
            environment = None

        root = find_project_root()
        project = load_project_config(root)
        config_dir = root / project.config_dir
        app_dir = root / project.app_dir

        branch = None if environment else current_git_branch(root)
        env_name, provenance = resolve_environment(
            environment, branch, project.branch_pattern, known_environments(config_dir)
        )
        env_config = load_environment(env_name, config_dir, project.feature_fallback)

        regions = order_regions(env_config, verb, requested_regions, all_regions)
        if regions is None:
            regions = _pick_regions(verb, env_name, env_config, plain)

        commands = compose_commands(
            verb, env_name, env_config, regions, project, extra_args, app_dir, root
        )
        ui.plan(env_name, provenance, env_config, commands)

        if dry_run:
            for command in commands:
                if command.pre_hook:
                    ui.echo_hook(command.pre_hook.command, "pre")
                ui.echo_command(command)
                if command.post_hook:
                    ui.echo_hook(command.post_hook.command, "post")
            return 0

        results = run_commands(commands, ui)
        ui.summary(env_name, results)
        failed = next((r for r in results if r.status == "failed"), None)
        return failed.exit_code if failed and failed.exit_code else 0
    except CdkwError as exc:
        ui.error(str(exc))
        return exc.exit_code


def _pick_regions(verb: str, env_name: str, env_config: EnvironmentConfig, plain: bool) -> list[str]:
    """Interactive checklist for mutating verbs without a region selection; hard error otherwise."""
    single = verb in SINGLE_REGION_VERBS
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not plain
    if not interactive:
        hint = "pass --region" if single else "pass --region or --all-regions"
        raise CdkwError(f"cdk {verb} does not fan out silently — {hint}")
    import questionary

    ordered = default_region_order(env_config, verb)
    primary = env_config.primary_region
    choices = [
        questionary.Choice(title=f"{name} (primary)" if name == primary else name, value=name)
        for name in ordered
    ]
    if single:
        picked = questionary.select(f"{verb} {env_name} — select a region:", choices=choices).ask()
        selected = [picked] if picked else None
    else:
        selected = questionary.checkbox(
            f"{verb} {env_name} — select regions (listed in run order):", choices=choices
        ).ask()
    if not selected:
        raise CdkwError("no regions selected — aborted")
    return selected
