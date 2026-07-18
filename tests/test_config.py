import pytest

from cdkw.config import (
    ProjectConfig,
    find_project_root,
    known_environments,
    load_environment,
    load_project_config,
)
from cdkw.errors import CdkwError


@pytest.fixture
def config_dir(tmp_path):
    directory = tmp_path / "environments"
    directory.mkdir()
    (directory / "test-main.yaml").write_text(
        "account: '111'\nstage: test\nregions:\n  us-east-1:\n    is_primary: true\n"
    )
    (directory / "dev-feature.yaml").write_text(
        "account: '111'\nprofile: account-test\nstage: test\n"
        "regions:\n  eu-central-1:\n    is_primary: true\n  us-east-1: {}\n"
    )
    return directory


class TestEnvironmentLookup:
    def test_exact_file_wins(self, config_dir):
        config = load_environment("test-main", config_dir)
        assert config.stage == "test"
        assert config.primary_region == "us-east-1"

    def test_feature_falls_back_to_shared_config(self, config_dir):
        config = load_environment("feature-123", config_dir)
        assert config.profile == "account-test"
        assert list(config.regions) == ["eu-central-1", "us-east-1"]
        assert config.primary_region == "eu-central-1"

    def test_unknown_environment_lists_known(self, config_dir):
        with pytest.raises(CdkwError, match="dev-feature, test-main"):
            load_environment("prod-main", config_dir)

    def test_non_feature_name_does_not_fall_back(self, config_dir):
        with pytest.raises(CdkwError):
            load_environment("stage-nft", config_dir)

    def test_app_specific_keys_are_tolerated(self, config_dir):
        (config_dir / "custom.yaml").write_text(
            "account: '111'\nstage: test\nfoo: bar\nregions:\n  us-east-1: {}\n"
        )
        config = load_environment("custom", config_dir)
        assert config.primary_region is None

    def test_known_environments_sorted(self, config_dir):
        assert known_environments(config_dir) == ["dev-feature", "test-main"]


class TestProjectConfig:
    def test_defaults_match_workspace_conventions(self):
        config = ProjectConfig()
        assert config.config_dir == "environments"
        assert config.env_context_key == "env"
        assert config.stack_pattern == "{environment}-{region_short}/*"
        assert config.feature_fallback == "dev-feature"

    def test_missing_file_yields_defaults(self, tmp_path):
        assert load_project_config(tmp_path) == ProjectConfig()

    def test_overrides_from_cdkw_yml(self, tmp_path):
        (tmp_path / "cdkw.yml").write_text("env_context_key: stage\nconfig_dir: config\n")
        config = load_project_config(tmp_path)
        assert config.env_context_key == "stage"
        assert config.config_dir == "config"

    def test_unknown_keys_rejected(self, tmp_path):
        (tmp_path / "cdkw.yml").write_text("no_such_key: 1\n")
        with pytest.raises(CdkwError, match="invalid"):
            load_project_config(tmp_path)

    def test_hooks_default_empty(self):
        config = ProjectConfig()
        assert config.hooks.pre is None
        assert config.hooks.post is None

    def test_hooks_from_cdkw_yml(self, tmp_path):
        (tmp_path / "cdkw.yml").write_text(
            "hooks:\n  pre: uv run scripts/prepare.py\n  post: uv run scripts/tag.py\n"
        )
        config = load_project_config(tmp_path)
        assert config.hooks.pre == "uv run scripts/prepare.py"
        assert config.hooks.post == "uv run scripts/tag.py"

    def test_unknown_hook_keys_rejected(self, tmp_path):
        (tmp_path / "cdkw.yml").write_text("hooks:\n  pre_deploy: echo hi\n")
        with pytest.raises(CdkwError, match="invalid"):
            load_project_config(tmp_path)


class TestProjectRoot:
    def test_found_via_cdk_json_walking_up(self, tmp_path):
        (tmp_path / "cdk.json").write_text("{}")
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert find_project_root(nested) == tmp_path

    def test_missing_markers_error(self, tmp_path):
        with pytest.raises(CdkwError, match="no cdkw.yml or cdk.json"):
            find_project_root(tmp_path)
