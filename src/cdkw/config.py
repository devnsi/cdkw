"""Configuration loading: project config (.cdkw.yaml) and per-environment YAML files.

The environment schema mirrors workspace/src/config/environment.py — the wrapper and app.py
must agree on the same files.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from cdkw.errors import CdkwError

CONFIG_NAMES = (".cdkw.yaml", ".cdkw.yml", "cdkw.yaml", "cdkw.yml")


class RegionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    is_primary: bool = False


class EnvironmentConfig(BaseModel):
    """One environment's YAML file; arbitrary app-specific keys are tolerated, not interpreted."""

    model_config = ConfigDict(extra="allow")

    account: str
    profile: str | None = None
    stage: str
    regions: dict[str, RegionConfig] = {}  # empty/omitted ⇒ regionless environment

    @field_validator("regions", mode="before")
    @classmethod
    def _bare_regions_key(cls, value: object) -> object:
        # a bare `regions:` key in YAML loads as None
        return {} if value is None else value

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
    """Optional .cdkw.yaml at the project root; defaults match the workspace conventions."""

    model_config = ConfigDict(extra="forbid")

    config_dir: str = "environments"
    app_dir: str = "."
    branch_pattern: str = r"feature/[A-Za-z]+-(?P<num>\d+).*"
    env_context_key: str = "env"
    stack_pattern: str = "{environment}-{region_short}/*"
    stack_pattern_regionless: str = "{environment}/*"
    feature_fallback: str = "dev-feature"
    hooks: HooksConfig = HooksConfig()

    @field_validator("stack_pattern_regionless")
    @classmethod
    def _no_region_placeholders(cls, value: str) -> str:
        if "{region}" in value or "{region_short}" in value:
            raise ValueError(
                "stack_pattern_regionless renders per environment alone — "
                "{region}/{region_short} are invalid here"
            )
        return value


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default: cwd) to the first directory holding a config or cdk.json."""
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "cdk.json").exists() or any(
            (candidate / name).exists() for name in CONFIG_NAMES
        ):
            return candidate
    raise CdkwError(
        f"no .cdkw.yaml or cdk.json found in {start} or any parent — run cdkw inside a CDK project"
    )


def find_project_config(root: Path) -> Path | None:
    """The project config in `root`, if any; two accepted names at once is an error, not a guess."""
    found = [root / name for name in CONFIG_NAMES if (root / name).exists()]
    if len(found) > 1:
        names = ", ".join(path.name for path in found)
        raise CdkwError(
            f"multiple cdkw configs in {root}: {names} — keep one (.cdkw.yaml recommended)"
        )
    return found[0] if found else None


def load_project_config(root: Path) -> ProjectConfig:
    path = find_project_config(root)
    if path is None:
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
