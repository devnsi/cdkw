from pathlib import Path

import yaml
from pydantic import BaseModel

ENVIRONMENTS_DIR = Path(__file__).resolve().parents[2] / "environments"
FEATURE_FALLBACK = "dev-feature"


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
