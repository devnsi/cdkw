import pytest

from cdkw.config import EnvironmentConfig, ProjectConfig


@pytest.fixture
def env_config() -> EnvironmentConfig:
    return EnvironmentConfig.model_validate(
        {
            "account": "111111111111",
            "profile": "account-test",
            "stage": "test",
            "regions": {
                "eu-central-1": {"is_primary": False},
                "us-east-1": {"is_primary": True},
                "ap-south-1": {"is_primary": False},
            },
        }
    )


@pytest.fixture
def regionless_env_config() -> EnvironmentConfig:
    return EnvironmentConfig.model_validate(
        {
            "account": "111111111111",
            "profile": "account-test",
            "stage": "test",
        }
    )


@pytest.fixture
def project_config() -> ProjectConfig:
    return ProjectConfig()
