"""Environment and region resolution — pure functions over config + arguments."""

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from cdkw.config import EnvironmentConfig
from cdkw.errors import CdkwError

MUTATING_VERBS = frozenset({"deploy", "destroy"})


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
    if requested:
        unknown = [r for r in requested if r not in config.regions]
        if unknown:
            raise CdkwError(
                f"region(s) not configured for this environment: {', '.join(unknown)}\n"
                f"  known regions: {', '.join(config.regions)}"
            )
        return list(requested)
    if all_regions or verb not in MUTATING_VERBS:
        return default_region_order(config, verb)
    return None
