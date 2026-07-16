# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Greenfield project — no code exists yet, only the README describing the goal. There is no build system, test runner, or linter to document until the implementation approach is chosen.

## Goal

Build a CLI/TUI tool (likely Python, or an evaluated off-the-shelf alternative) that wraps AWS CDK commands (`synth`, `diff`, `deploy`, `destroy`) to manage multi-stage, multi-environment, multi-region deployments. It replaces a set of modular justfile recipes that became unwieldy due to combinatorics.

## Domain Terminology (important — terms are easily confused)

- **Stage**: one of `test`, `stage`, `prod` — differentiated by separate AWS accounts (e.g. account A = test, account B = stage, account C = prod). Not the same as a CDK stage.
- **Environment**: a full standalone provisioning of the application (e.g. `feature-123`, `stage-main`, `stage-nft`). Multiple logical environments can live in the same account/stage.
- Each environment has its own YAML config file, **except** feature environments, which share a common config instantiated per feature.
- Each environment can deploy to up to 4 regions (a `region` key in its YAML). Each region per environment is synthesized as its own template (independent CDK stage). A **primary region** may provide global resources and should usually be deployed first.

## Key Mechanics

- CDK runs `app.py` to synthesize templates from Python code.
- Logical environments in the same account are differentiated by a parameter passed to CDK commands: `--env stage=feature-123`.
- The active feature environment can be derived from the git branch name (e.g. `feature/ABC-123-some-test` → `feature-123`).
- The tool must give granular control over which environment deploys to which region, one region at a time (e.g. deploy `test-main` to `us-east-1`, then `us-west-1`).