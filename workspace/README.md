# Workspace for CDK Wrapper

Minimal runnable CDK app matching the conventions in [DESIGN.md](../DESIGN.md). Uses uv as
package manager; the CDK CLI comes from npm (`npx cdk` works without a global install).

## Layout

- `src/app.py` — CDK app entry point (`cdk.json` runs it via `uv run python -m src.app`).
  Reads the environment from `--context env=<environment>`, loads its YAML, and creates one
  `cdk.Stage` per configured region, named `<environment>-<region>`.
- `src/config/environment.py` — pydantic model + loader for the environment YAML. Lookup is
  exact file name first (`environments/<env>.yaml`), then `feature-*` environments fall back
  to the shared `environments/dev-feature.yaml`.
- `environments/dev-feature.yaml` — example config: account/stage plus a region map with an
  `is_primary` flag.

## Run it

```sh
uv sync                                                   # once

npx cdk list  --context env=feature-123                   # all regions
npx cdk synth --context env=feature-123 --quiet
npx cdk synth --context env=feature-123 --context region=us-east-1   # single region
```

Single-region targeting also honors `CDK_DEPLOY_REGION` (context wins). Unknown environments
and regions fail with a message listing the known ones.

Note: on Windows, jsii sometimes prints an `ENOTEMPTY` temp-dir cleanup error *after* a
successful synth — cosmetic, safe to ignore (check for `Successfully synthesized`).
