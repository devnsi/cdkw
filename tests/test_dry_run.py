"""Integration: run the CLI with --dry-run against workspace/ — no AWS, no cdk binary needed."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cdkw.cli import app

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
        first = output.index('"feature-123-eu-central-1/*"')  # primary
        second = output.index('"feature-123-us-east-1/*"')
        assert first < second
        assert "--context env=feature-123" in output
        assert "--profile account-test" in output

    def test_single_region_targeting(self):
        result = runner.invoke(app, ["deploy", "feature-123", "-r", "us-east-1", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        output = combined_output(result)
        assert '$ npx cdk deploy "feature-123-us-east-1/*"' in output
        assert "eu-central-1/*" not in output

    def test_destroy_all_regions_reversed_primary_last(self):
        result = runner.invoke(app, ["destroy", "feature-123", "--all-regions", "--dry-run", "--plain"])
        assert result.exit_code == 0, combined_output(result)
        output = combined_output(result)
        assert output.index("us-east-1/*") < output.index("eu-central-1/*")

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


class TestErrors:
    def test_deploy_without_region_fails_without_tty(self):
        result = runner.invoke(app, ["deploy", "feature-123"])
        assert result.exit_code == 2
        assert "--region or --all-regions" in combined_output(result)

    def test_unknown_region(self):
        result = runner.invoke(app, ["synth", "feature-123", "-r", "mars-1", "--plain"])
        assert result.exit_code == 2
        assert "mars-1" in combined_output(result)

    def test_unknown_environment_lists_known(self):
        result = runner.invoke(app, ["synth", "prod-main", "--plain"])
        assert result.exit_code == 2
        assert "dev-feature" in combined_output(result)
