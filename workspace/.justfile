#!/usr/bin/env just --justfile

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set windows-shell := ["sh.exe", "-eu", "-o", "pipefail", "-c"]
set quiet := true

# Explain how to use the recipes.
[default]
[private]
default:
    just --list

# Synthesize the template for the environment.
[script]
synth:
    cdk diff "feature-123*/*" --context env=feature-123
