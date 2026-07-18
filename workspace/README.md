# Workspace for CDK Wrapper

Minimal runnable CDK app matching the conventions in [DESIGN.md](../DESIGN.md). Uses uv as
package manager; the CDK CLI comes from npm (`npx cdk` works without a global install).

## Layout

- `src/app.py` — CDK app entry point (`cdk.json` runs it via `uv run python -m src.app`).
  Reads the environment from `--context env=<environment>`, loads its YAML, and creates one
  `cdk.Stage` per configured region, named `<environment>-<region_short>`. A regionless
  environment (no `regions` map, e.g. `local`) gets a single stage named
  `<environment>` — no region suffix.
- `src/config/environment.py` — pydantic model + loader for the environment YAML. Lookup is
  exact file name first (`environments/<env>.yaml`), then `feature-*` environments fall back
  to the shared `environments/dev-feature.yaml`.
- `environments/` — example configs: `dev-feature.yaml` (shared by all `feature-*`
  environments; account/stage plus a region map with an `is_primary` flag),
  `test-integration.yaml` and `stage-check.yaml` (fixed environments), and `local.yaml`
  (regionless — no `regions` map).
- `cdkw.yml` + `scripts/hook_pre.py` / `scripts/hook_post.sh` — sample cdkw hooks that print
  a brief message with their `CDKW_*` context.

## Run it

```sh
uv sync                                                   # once

npx cdk list  --context env=feature-123                   # all regions
npx cdk synth --context env=feature-123 --quiet
npx cdk synth --context env=feature-123 --context region=us-east-1   # single region
npx cdk list  --context env=local                         # regionless: one stage, no suffix
```

Single-region targeting also honors `CDK_DEPLOY_REGION` (context wins). Unknown environments
and regions fail with a message listing the known ones.

Note: on Windows, jsii sometimes prints an `ENOTEMPTY` temp-dir cleanup error *after* a
successful synth — cosmetic, safe to ignore (check for `Successfully synthesized`).
