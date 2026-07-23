# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cdkw`, a Python CLI wrapping AWS CDK commands for multi-stage, multi-environment, multi-region
deployments. Docs are split by audience — don't duplicate content across them:

- [README.md](README.md) — user-facing: what/why, terminology, installation, usage.
- [DESIGN.md](DESIGN.md) — the behavior contract: CLI surface, config schemas, command
  composition, ordering rules, output design. Consult it before changing wrapper behavior.
- [workspace/README.md](workspace/README.md) — the runnable example CDK app the wrapper drives;
  the reference for the conventions the wrapper must match.

## Layout & commands

- `src/cdkw/` — the wrapper (typer CLI); `tests/` — pure-function unit tests plus `--dry-run`
  snapshot tests, no AWS needed.
- Run tests: `uv run pytest`
- Real end-to-end runs: from `workspace/`, e.g. `uv run --project .. cdkw synth feature-123`
  (cdkw finds the project root via `cdk.json`/`.cdkw.yaml`; the workspace needs `uv sync` and npm's CDK CLI once).

## Terminology trap

**Stage** here means `test`/`stage`/`prod` — a separate AWS account. It is *not* a CDK stage
(each environment+region pair is its own CDK stage). Full definitions in the
[README](README.md#terminology).
