from pathlib import Path

import yaml
from pydantic import BaseModel

ENVIRONMENTS_DIR = Path(__file__).resolve().parents[2] / "environments"
FEATURE_FALLBACK = "dev-feature"

_COMPOUND_DIRECTIONS = {"northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw"}


def region_short(region: str) -> str:
    """Abbreviate an AWS region name: us-east-1 → use1, ap-southeast-1 → apse1."""
    parts = region.split("-")
    if len(parts) < 3:
        raise SystemExit(f"cannot abbreviate region '{region}': expected a name like 'us-east-1'")
    return parts[0] + "".join(_COMPOUND_DIRECTIONS.get(p, p[:1]) for p in parts[1:-1]) + parts[-1]


class RegionConfig(BaseModel):
    is_primary: bool = False


class EnvironmentConfig(BaseModel):
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

    @classmethod
    def load(cls, env_name: str, config_dir: Path = ENVIRONMENTS_DIR) -> "EnvironmentConfig":
        """Exact config file first; feature environments fall back to the shared one."""
        path = config_dir / f"{env_name}.yaml"
        if not path.exists() and env_name.startswith("feature-"):
            path = config_dir / f"{FEATURE_FALLBACK}.yaml"
        if not path.exists():
            known = sorted(p.stem for p in config_dir.glob("*.yaml"))
            raise FileNotFoundError(
                f"no config for environment '{env_name}' in {config_dir} (known: {', '.join(known)})"
            )
        return cls.model_validate(yaml.safe_load(path.read_text()))
