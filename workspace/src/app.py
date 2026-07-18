import os

import aws_cdk as cdk
from constructs import Construct

from src.config.environment import EnvironmentConfig, region_short


class AppStage(cdk.Stage):
    """One standalone provisioning of the application in a single region."""

    def __init__(
        self, scope: Construct, id: str, *, env_name: str, region: str | None, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)
        stack = cdk.Stack(self, "storage")
        cdk.CfnOutput(stack, "Environment", value=env_name)
        if region:
            cdk.CfnOutput(stack, "Region", value=region)


def main() -> None:
    app = cdk.App()

    env_name = app.node.try_get_context("env")
    if not env_name:
        raise SystemExit("missing environment: pass --context env=<environment>")
    config = EnvironmentConfig.load(env_name)

    # Optional single-region targeting; default is one stage per configured region.
    target = app.node.try_get_context("region") or os.environ.get("CDK_DEPLOY_REGION")
    if not config.regions:
        # Regionless environment: a single stage named without a region suffix.
        if target:
            raise SystemExit(f"environment '{env_name}' is regionless — drop region '{target}'")
        AppStage(
            app,
            env_name,
            env_name=env_name,
            region=None,
            env=cdk.Environment(account=config.account),
        )
    elif target and target not in config.regions:
        raise SystemExit(f"region '{target}' not configured for '{env_name}' "
                         f"(known: {', '.join(config.regions)})")

    for region in config.regions:
        if target and region != target:
            continue
        AppStage(
            app,
            f"{env_name}-{region_short(region)}",
            env_name=env_name,
            region=region,
            env=cdk.Environment(account=config.account, region=region),
        )

    print("Synthesized!")
    app.synth()


if __name__ == "__main__":
    main()
