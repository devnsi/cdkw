# CDK Wrapper

A CLI tool to manage AWS CDK deployments across multiple stages, environments, and regions.

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
- **Region**: each environment can be deployed to up to 4 AWS regions.

## Configuration model

Each environment is described by its own YAML file, which captures the differences per environment
(e.g. a `region` key listing the target regions). The exception is feature environments: they share
a single common YAML file that is instantiated per feature.

Example YAML files:

- `dev-feature` (with region: us-east-1) — shared by all feature environments
- `test-main`
- `stage-main`
- `stage-nft` (with regions: us-east-1, eu-central-1)
- `prod-main` (with regions: us-east-1, eu-central-1)

Which yields concrete deployments such as:

- `feature-123` on test (based on the shared feature config, in account A)
- `feature-234` on test (based on the shared feature config, in account A)
- `test-main` on test (in account A)
- `stage-main` on stage (in account B)
- `stage-nft` on stage (in account B)
- `prod-main` on prod (in account C)

## Deployment mechanics

- Each region of an environment is synthesized as its own template (an independent CDK stage).
- There can be a **primary region** providing global resources; it should usually be deployed first.
- Since multiple logical environments live in the same account, the environment is passed to CDK
  commands as a parameter: `--env stage=feature-123`.
- The currently active feature environment can be derived from the git branch name
  (e.g. `feature/ABC-123-some-test` → `feature-123`).

## Requirements for the tool

- Granular control over which environment is deployed to which region — e.g. deploy `test-main`
  to `us-east-1`, then `us-west-1`, one at a time.
- Support the common CDK commands (`synth`, `diff`, `deploy`, `destroy`) for each
  environment/region combination.

## Approach

We were previously using modular justfile recipes to bridge the gap between simple CDK commands and
multi-regional, multi-stage, multi-environment deployments, but the combinatorics call for more
generalized CLI tooling. This could be either an existing open-source tool (if any supports these
use cases) or a custom Python CLI/TUI.
