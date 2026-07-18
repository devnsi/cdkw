#!/usr/bin/env just --justfile

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set windows-shell := ["sh.exe", "-eu", "-o", "pipefail", "-c"]
set quiet := true

# Explain how to use the recipes.
[default]
[private]
default:
    just --list

# Install the package and its dependencies.
sync:
    uv sync

# Run the test suite (pure unit tests + --dry-run CLI tests; no AWS needed).
test:
    uv run pytest

# Run cdkw against the example workspace (e.g. `just cdkw synth feature-123 --dry-run`).
cdkw *args:
    cd workspace && uv run --project .. cdkw {{ args }}

# Preview the composed cdk commands for the example environment without executing.
demo:
    cd workspace && uv run --project .. cdkw synth feature-123 --dry-run

# Install locally from source.
[script]
install:
    uv build
    latest=$(ls -t dist | grep .whl | head -n 1)
    uv tool install "dist/$latest" --force
