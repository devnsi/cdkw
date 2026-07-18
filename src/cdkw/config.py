"""Configuration loading: project config (cdkw.yml) and per-environment YAML files.

The environment schema mirrors workspace/src/config/environment.py — the wrapper and app.py
must agree on the same files.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from cdkw.errors import CdkwError


class RegionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    is_primary: bool = False


class EnvironmentConfig(BaseModel):
    """One environment's YAML file; arbitrary app-specific keys are tolerated, not interpreted."""

    model_config = ConfigDict(extra="allow")

    account: str
    profile: str | None = None
    stage: str
    regions: dict[str, RegionConfig]

    @property
    def primary_region(self) -> str | None:
        for name, region in self.regions.items():
            if region.is_primary:
                return name
        return None


class HooksConfig(BaseModel):
    """User shell commands run around each composed cdk command (see DESIGN.md: Hooks)."""

    model_config = ConfigDict(extra="forbid")

    pre: str | None = None
    post: str | None = None


class ProjectConfig(BaseModel):
    """Optional cdkw.yml at the project root; defaults match the workspace conventions."""

    model_config = ConfigDict(extra="forbid")

    config_dir: str = "environments"
    app_dir: str = "."
    branch_pattern: str = r"feature/[A-Za-z]+-(?P<num>\d+).*"
    env_context_key: str = "env"
    stack_pattern: str = "{environment}-{region_short}/*"
    feature_fallback: str = "dev-feature"
    hooks: HooksConfig = HooksConfig()


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default: cwd) to the first directory holding cdkw.yml or cdk.json."""
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "cdkw.yml").exists() or (candidate / "cdk.json").exists():
            return candidate
    raise CdkwError(
        f"no cdkw.yml or cdk.json found in {start} or any parent — run cdkw inside a CDK project"
    )


def load_project_config(root: Path) -> ProjectConfig:
    path = root / "cdkw.yml"
    if not path.exists():
        return ProjectConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise CdkwError(f"invalid {path}:\n{exc}") from exc


def known_environments(config_dir: Path) -> list[str]:
    return sorted(p.stem for p in config_dir.glob("*.yaml"))


def load_environment(
    env_name: str, config_dir: Path, feature_fallback: str = "dev-feature"
) -> EnvironmentConfig:
    """Exact config file first; feature environments fall back to the shared one."""
    path = config_dir / f"{env_name}.yaml"
    if not path.exists() and env_name.startswith("feature-"):
        path = config_dir / f"{feature_fallback}.yaml"
    if not path.exists():
        known = ", ".join(known_environments(config_dir)) or "none"
        raise CdkwError(f"no config for environment '{env_name}' in {config_dir} (known: {known})")
    try:
        return EnvironmentConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        raise CdkwError(f"invalid environment config {path}:\n{exc}") from exc
