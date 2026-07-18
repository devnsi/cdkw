"""Environment and region resolution — pure functions over config + arguments."""

import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

from cdkw.config import EnvironmentConfig
from cdkw.errors import CdkwError

MUTATING_VERBS = frozenset({"deploy", "destroy", "watch"})
SINGLE_REGION_VERBS = frozenset({"watch"})

_COMPOUND_DIRECTIONS = {"northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw"}


def region_short(region: str) -> str:
    """Abbreviate an AWS region name: us-east-1 → use1, ap-southeast-1 → apse1."""
    parts = region.split("-")
    if len(parts) < 3:
        return region
    return parts[0] + "".join(_COMPOUND_DIRECTIONS.get(p, p[:1]) for p in parts[1:-1]) + parts[-1]


def region_shortcodes(regions: Iterable[str]) -> dict[str, str]:
    """Shortcode per region, refusing collisions (two regions → one selector/stage id)."""
    by_short: dict[str, str] = {}
    codes: dict[str, str] = {}
    for region in regions:
        short = region_short(region)
        clash = by_short.get(short)
        if clash:
            raise CdkwError(
                f"region shortcodes collide: '{clash}' and '{region}' both abbreviate to "
                f"'{short}' — use {{region}} in stack_pattern"
            )
        by_short[short] = region
        codes[region] = short
    return codes


def current_git_branch(cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def resolve_environment(
    explicit: str | None,
    branch: str | None,
    branch_pattern: str,
    known: Sequence[str],
) -> tuple[str, str]:
    """Resolve the environment name and where it came from: flag > git branch > error."""
    if explicit:
        return explicit, "explicit"
    if branch:
        match = re.match(branch_pattern, branch)
        if match:
            if "num" not in match.groupdict():
                raise CdkwError(
                    f"branch_pattern {branch_pattern!r} must define a named group (?P<num>...)"
                )
            return f"feature-{match['num']}", f"from branch {branch}"
    known_list = ", ".join(known) or "none found"
    raise CdkwError(
        "cannot resolve environment: pass it as an argument or check out a feature branch\n"
        f"  branch: {branch or '(none)'}\n"
        f"  known environments: {known_list}"
    )


def default_region_order(config: EnvironmentConfig, verb: str) -> list[str]:
    """Primary first, then config declaration order; destroy runs the reverse (primary last)."""
    regions = list(config.regions)
    primary = config.primary_region
    if primary:
        regions.remove(primary)
        regions.insert(0, primary)
    if verb == "destroy":
        regions.reverse()
    return regions


def order_regions(
    config: EnvironmentConfig,
    verb: str,
    requested: Sequence[str],
    all_regions: bool,
) -> list[str] | None:
    """Return the regions to run, in order; None means a selection is still required.

    Explicit --region values run in the given order. --all-regions (and the default for
    non-mutating verbs) uses the primary-first ordering. Mutating verbs without a selection
    return None so the CLI can prompt interactively or fail.
    """
    if verb in SINGLE_REGION_VERBS:
        if all_regions or len(requested) > 1:
            raise CdkwError(f"cdk {verb} runs a single region until interrupted — pass one --region")
    if requested:
        by_short: dict[str, str] | None = None
        resolved: list[str] = []
        unknown: list[str] = []
        for value in requested:
            if value in config.regions:
                resolved.append(value)
                continue
            if by_short is None:
                by_short = {s: r for r, s in region_shortcodes(config.regions).items()}
            expanded = by_short.get(value)
            if expanded:
                resolved.append(expanded)
            else:
                unknown.append(value)
        if unknown:
            known = ", ".join(f"{r} ({region_short(r)})" for r in config.regions)
            raise CdkwError(
                f"region(s) not configured for this environment: {', '.join(unknown)}\n"
                f"  known regions: {known}"
            )
        return resolved
    if all_regions or verb not in MUTATING_VERBS:
        return default_region_order(config, verb)
    return None
