from pathlib import Path

import pytest

from cdkw.compose import compose_commands
from cdkw.config import ProjectConfig
from cdkw.errors import CdkwError

APP_DIR = Path("app")


class TestComposition:
    def test_one_command_per_region_in_order(self, env_config, project_config):
        commands = compose_commands(
            "deploy", "feature-123", env_config, ["us-east-1", "eu-central-1"], project_config, [], APP_DIR
        )
        assert [c.region for c in commands] == ["us-east-1", "eu-central-1"]
        assert all(c.cwd == APP_DIR for c in commands)

    def test_full_argv(self, env_config, project_config):
        (command,) = compose_commands(
            "deploy", "feature-123", env_config, ["us-east-1"], project_config, [], APP_DIR
        )
        assert command.argv == [
            "npx",
            "cdk",
            "deploy",
            "feature-123-use1/*",
            "--context",
            "env=feature-123",
            "--context",
            "region=us-east-1",
            "--profile",
            "account-test",
        ]

    def test_no_profile_when_unset(self, env_config, project_config):
        env_config.profile = None
        (command,) = compose_commands(
            "synth", "feature-123", env_config, ["us-east-1"], project_config, [], APP_DIR
        )
        assert "--profile" not in command.argv

    def test_extra_args_appended_untouched(self, env_config, project_config):
        (command,) = compose_commands(
            "deploy",
            "prod-main",
            env_config,
            ["us-east-1"],
            project_config,
            ["--require-approval", "never"],
            APP_DIR,
        )
        assert command.argv[-2:] == ["--require-approval", "never"]

    def test_project_config_overrides_shape_the_command(self, env_config):
        project = ProjectConfig(env_context_key="stage", stack_pattern="{environment}/{region}")
        (command,) = compose_commands(
            "diff", "stage-nft", env_config, ["eu-central-1"], project, [], APP_DIR
        )
        assert "stage=stage-nft" in command.argv
        assert command.selector == "stage-nft/eu-central-1"

    def test_region_pattern_tolerates_unabbreviatable_region_keys(self, env_config):
        env_config.regions["local"] = type(env_config.regions["us-east-1"])()
        project = ProjectConfig(stack_pattern="{environment}-{region}/*")
        (command,) = compose_commands(
            "synth", "feature-123", env_config, ["local"], project, [], APP_DIR
        )
        assert command.selector == "feature-123-local/*"

    def test_colliding_shortcodes_error_before_any_command(self, env_config, project_config):
        env_config.regions["ap-southwest-1"] = type(env_config.regions["ap-south-1"])()
        env_config.regions["ap-so-west-1"] = type(env_config.regions["ap-south-1"])()
        with pytest.raises(CdkwError, match="collide"):
            compose_commands(
                "deploy", "feature-123", env_config, ["us-east-1"], project_config, [], APP_DIR
            )

    def test_display_is_copy_pasteable_with_quoted_selector(self, env_config, project_config):
        (command,) = compose_commands(
            "deploy", "feature-123", env_config, ["us-east-1"], project_config, [], APP_DIR
        )
        assert command.display.startswith('npx cdk deploy "feature-123-use1/*"')
        assert "--context env=feature-123" in command.display


class TestHooks:
    ROOT = Path("root")

    def hooks_project(self) -> ProjectConfig:
        return ProjectConfig(hooks={"pre": "echo pre", "post": "echo post"})

    def test_no_hooks_by_default(self, env_config, project_config):
        (command,) = compose_commands(
            "deploy", "feature-123", env_config, ["us-east-1"], project_config, [], APP_DIR
        )
        assert command.pre_hook is None
        assert command.post_hook is None

    def test_hooks_attached_with_root_cwd_and_context_env(self, env_config):
        (command,) = compose_commands(
            "deploy", "feature-123", env_config, ["us-east-1"], self.hooks_project(), [],
            APP_DIR, self.ROOT,
        )
        assert command.pre_hook.command == "echo pre"
        assert command.post_hook.command == "echo post"
        assert command.pre_hook.cwd == self.ROOT
        assert command.pre_hook.env == {
            "CDKW_VERB": "deploy",
            "CDKW_ENVIRONMENT": "feature-123",
            "CDKW_STAGE": "test",
            "CDKW_ACCOUNT": "111111111111",
            "CDKW_PROFILE": "account-test",
            "CDKW_REGION": "us-east-1",
            "CDKW_REGION_SHORT": "use1",
        }
        assert command.post_hook.env == command.pre_hook.env

    def test_profile_empty_when_unset(self, env_config):
        env_config.profile = None
        (command,) = compose_commands(
            "synth", "feature-123", env_config, ["us-east-1"], self.hooks_project(), [],
            APP_DIR, self.ROOT,
        )
        assert command.pre_hook.env["CDKW_PROFILE"] == ""

    def test_hooks_attached_per_region(self, env_config):
        commands = compose_commands(
            "deploy", "feature-123", env_config, ["us-east-1", "eu-central-1"],
            self.hooks_project(), [], APP_DIR, self.ROOT,
        )
        assert [c.pre_hook.env["CDKW_REGION"] for c in commands] == ["us-east-1", "eu-central-1"]
        assert [c.pre_hook.env["CDKW_REGION_SHORT"] for c in commands] == ["use1", "euc1"]

    def test_unabbreviatable_region_is_its_own_shortcode(self, env_config):
        env_config.regions["local"] = type(env_config.regions["us-east-1"])()
        project = ProjectConfig(
            stack_pattern="{environment}-{region}/*", hooks={"pre": "echo pre"}
        )
        (command,) = compose_commands(
            "synth", "feature-123", env_config, ["local"], project, [], APP_DIR, self.ROOT
        )
        assert command.pre_hook.env["CDKW_REGION_SHORT"] == "local"
