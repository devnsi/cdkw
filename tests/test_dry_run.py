"""Integration: run the CLI with --dry-run against workspace/ — no AWS, no cdk binary needed."""

import importlib.util
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cdkw.cli import app
from cdkw.resolve import region_short

WORKSPACE = Path(__file__).resolve().parents[1] / "workspace"
runner = CliRunner()


def combined_output(result) -> str:
    try:
        return result.output + result.stderr
    except ValueError:  # older click mixes stderr into output
        return result.output


@pytest.fixture(autouse=True)
def in_workspace(monkeypatch):
    monkeypatch.chdir(WORKSPACE)


class TestDryRun:
    def test_synth_all_regions_primary_first(self):
        result = runner.invoke(app, ["synth", "feature-123", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        output = combined_output(result)
        first = output.index('"feature-123-euc1/*"')  # primary
        second = output.index('"feature-123-use1/*"')
        assert first < second
        assert "--context env=feature-123" in output
        assert "--profile account-test" in output

    def test_single_region_targeting(self):
        result = runner.invoke(app, ["deploy", "feature-123", "-r", "us-east-1", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        output = combined_output(result)
        assert '$ npx cdk deploy "feature-123-use1/*"' in output
        assert "euc1/*" not in output

    def test_single_region_targeting_by_shortcode(self):
        result = runner.invoke(app, ["deploy", "feature-123", "-r", "use1", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        output = combined_output(result)
        assert '$ npx cdk deploy "feature-123-use1/*"' in output
        assert "euc1/*" not in output

    def test_destroy_all_regions_reversed_primary_last(self):
        result = runner.invoke(app, ["destroy", "feature-123", "--all-regions", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        output = combined_output(result)
        assert output.index("use1/*") < output.index("euc1/*")

    def test_watch_single_region(self):
        result = runner.invoke(app, ["watch", "feature-123", "-r", "us-east-1", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        assert '$ npx cdk watch "feature-123-use1/*"' in combined_output(result)

    def test_extra_args_pass_through(self):
        result = runner.invoke(
            app,
            ["deploy", "feature-123", "-r", "us-east-1", "--dry-run", "--plain", "--", "--require-approval", "never"],
        )
        assert result.exit_code == 0, combined_output(result)
        assert "--require-approval never" in combined_output(result)

    def test_plan_block_shows_provenance_and_stage(self):
        result = runner.invoke(app, ["synth", "feature-123", "--dry-run", "--plain"])
        output = combined_output(result)
        assert "environment" in output and "(explicit)" in output
        assert "test" in output and "12345" in output

    def test_quiet_suppresses_plan_but_keeps_commands(self):
        result = runner.invoke(app, ["synth", "feature-123", "--dry-run", "--plain", "--quiet"])
        output = combined_output(result)
        assert "plan" not in output
        assert "$ npx cdk synth" in output


class TestHooksDryRun:
    def test_hook_lines_shown_around_cdk_command(self, tmp_path, monkeypatch):
        (tmp_path / "cdk.json").write_text("{}")
        (tmp_path / "cdkw.yml").write_text(
            "hooks:\n  pre: uv run scripts/prepare.py\n  post: uv run scripts/tag.py\n"
        )
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        (env_dir / "test-main.yaml").write_text(
            "account: '111'\nstage: test\nregions:\n  us-east-1:\n    is_primary: true\n"
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["deploy", "test-main", "-r", "us-east-1", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        output = combined_output(result)
        assert "$ uv run scripts/prepare.py  (pre hook)" in output
        assert "$ uv run scripts/tag.py  (post hook)" in output
        assert output.index("prepare.py") < output.index("npx cdk deploy") < output.index("tag.py")


class TestWorkspaceContract:
    def test_workspace_region_short_matches_wrapper(self):
        """The app's stage ids and the wrapper's selectors are built from the same rule —
        the two copies of region_short must never drift apart."""
        spec = importlib.util.spec_from_file_location(
            "workspace_environment", WORKSPACE / "src" / "config" / "environment.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for region in [
            "us-east-1",
            "eu-central-1",
            "ap-south-1",
            "ap-southeast-1",
            "us-gov-west-1",
            "cn-northwest-1",
        ]:
            assert module.region_short(region) == region_short(region)


class TestErrors:
    def test_deploy_without_region_fails_without_tty(self):
        result = runner.invoke(app, ["deploy", "feature-123"])
        assert result.exit_code == 2
        assert "--region or --all-regions" in combined_output(result)

    def test_watch_without_region_fails_without_tty(self):
        result = runner.invoke(app, ["watch", "feature-123"])
        assert result.exit_code == 2
        assert "pass --region" in combined_output(result)

    def test_watch_all_regions_fails(self):
        result = runner.invoke(app, ["watch", "feature-123", "--all-regions", "--plain"])
        assert result.exit_code == 2
        assert "single region" in combined_output(result)

    def test_unknown_region(self):
        result = runner.invoke(app, ["synth", "feature-123", "-r", "mars-1", "--plain"])
        assert result.exit_code == 2
        assert "mars-1" in combined_output(result)

    def test_unknown_environment_lists_known(self):
        result = runner.invoke(app, ["synth", "prod-main", "--plain"])
        assert result.exit_code == 2
        assert "dev-feature" in combined_output(result)
