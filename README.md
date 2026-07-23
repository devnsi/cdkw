# CDK Wrapper

[![test](https://github.com/devnsi/cdkw/actions/workflows/test.yml/badge.svg)](https://github.com/devnsi/cdkw/actions/workflows/test.yml)

A CLI tool to manage AWS CDK deployments across multiple stages, environments, and regions.

## Installation

Run directly from GitHub with [uvx](https://docs.astral.sh/uv/guides/tools/) (no install step):

```sh
uvx --from git+https://github.com/devnsi/cdkw cdkw --help
```

Or install it as a persistent tool:

```sh
uv tool install git+https://github.com/devnsi/cdkw
cdkw --help
```

Requires Python >= 3.14 (uv provisions it automatically if missing).

For tab completion of verbs and environment names (installed tool only, not uvx), run
`cdkw --install-completion` once and restart the shell.

## Background

AWS CDK is a framework to describe AWS resources for provisioning. It comes as a Python library to
dynamically build CloudFormation templates: CDK runs an `app.py` to synthesize the templates from
Python code. The CDK CLI then operates on these templates (e.g. `synth`, `diff`, `deploy`).

In practice, an application is not deployed just once. It is deployed:

- to multiple **stages** (separate AWS accounts),
- as multiple **environments** within a stage (e.g. one per feature under development),
- and to multiple **regions** per environment.

Plain CDK commands do not cover this combinatorial space well, which is the gap this tool fills.

## Terminology

- **Stage**: one of `test`, `stage`, `prod`. Stages are differentiated by separate AWS accounts
  (e.g. account A for test, account B for stage, account C for prod).
- **Environment**: an encapsulated, full standalone provisioning of the application
  (e.g. `feature-123`, `stage-main`). Multiple environments can coexist in the same account/stage.
- **Region**: each environment can be deployed to multiple AWS regions — or none (a *regionless*
  environment, e.g. targeting local emulation like localstack).

## Configuration model

Each environment is described by its own YAML file (`environments/<environment>.yaml`), which
captures the differences per environment: the AWS account and stage, an optional AWS profile, and
a `regions` map marking the primary region. The exception is feature environments: they share a
single common YAML file that is instantiated per feature. The full schema — plus the optional
project-level `.cdkw.yaml` — is specified in [DESIGN.md](DESIGN.md#configuration).

Example YAML files:

- `dev-feature` (with region: us-east-1) — shared by all feature environments
- `test-main`
- `stage-main`
- `prod-main` (with regions: us-east-1, eu-central-1)

Which yields concrete deployments such as:

- `feature-123` on test (based on the shared feature config, in account A)
- `feature-234` on test (based on the shared feature config, in account A)
- `test-main` on test (in account A)
- `stage-main` on stage (in account B)
- `prod-main` on prod (in account C)

## Deployment mechanics

- Each region of an environment is synthesized as its own template (an independent CDK stage).
- There can be a **primary region** providing global resources; it should usually be deployed first.
- Since multiple logical environments live in the same account, the environment is passed to CDK
  commands as a parameter: `--context env=feature-123`.
- The currently active feature environment can be derived from the git branch name
  (e.g. `feature/ABC-123-some-test` → `feature-123`).

## Usage

`cdkw` mirrors the CDK verbs (`synth`, `diff`, `deploy`, `destroy`, `list`, `watch`) and gives granular
control over which environment goes to which region, one region at a time. Every run prints the
composed `cdk` command lines before executing them, so the raw CDK calls stay visible and
reproducible.

```sh
cdkw diff                                  # environment from git branch, all its regions
cdkw deploy test-main -r us-east-1         # one environment, one region
cdkw deploy test-main -r use1              # same, using the region shortcode
cdkw deploy test-main -r us-east-1 -r us-west-1   # explicit sequence
cdkw deploy test-main -r use1 -s Api       # only the Api stack in that region
cdkw deploy stage-nft --all-regions        # primary region first, then the rest
cdkw destroy feature-123 --all-regions     # reverse order: primary last
cdkw deploy prod-main -r eu-central-1 -- --require-approval never   # pass-through args
cdkw watch feature-123 -r us-east-1        # hot-deploy one region until interrupted
cdkw deploy local                          # regionless environment: exactly one command
```

On a terminal, `deploy`/`destroy`/`watch` hand CDK the real stdin/stdout, so CDK's own
security-approval and confirmation prompts just work — `--require-approval never` is only
needed in CI or piped runs. Passing it (or `--force` for `destroy`) also brings back the
dimmed, region-prefixed streaming, since no prompt can appear.

`cdkw <verb> --help` lists all options (`--dry-run`, `--quiet`, `--plain`, …); the full CLI
contract lives in [DESIGN.md](DESIGN.md#cli-surface).

### Hooks

Optional `pre`/`post` shell commands in `.cdkw.yaml` run around every composed `cdk` command,
with context passed as `CDKW_*` environment variables (`CDKW_VERB`, `CDKW_ENVIRONMENT`,
`CDKW_REGION`, `CDKW_REGION_SHORT`, …). For example, tagging what is deployed where:

```yaml
hooks:
  post: 'sh scripts/tag_deployment.sh'
```

```sh
# scripts/tag_deployment.sh — git-tag successful deploys, untag destroys
[ "$CDKW_EXIT_CODE" = "0" ] || exit 0
tag="env/$CDKW_ENVIRONMENT-$CDKW_REGION_SHORT"
case "$CDKW_VERB" in
  deploy)  git tag -f "$tag" ;;
  destroy) git tag -d "$tag" ;;
esac
```

A `pre` hook can also pass extra environment variables to the `cdk` process by writing
`KEY=VALUE` lines to the file named by `CDKW_ENV`. A failing `pre` hook stops the run like a
failing `cdk` command; `post` hooks always run (`CDKW_EXIT_CODE` tells them how the command
went) and a failing `post` hook is only a warning. Details in [DESIGN.md](DESIGN.md#hooks).
