# Design: `cdkw` — a thin CDK wrapper CLI

Design for the custom Python CLI recommended as the fallback in [RESEARCH.md](RESEARCH.md), after
the [Runway prototype](prototype/README.md) confirmed that per-environment region lists and
single-region targeting are not first-class there. Requirements come from the
[README](README.md).

## Guiding principle: stay close to CDK

The tool is a *command composer*, not an abstraction layer. Every invocation resolves to exactly
one visible `cdk` command per (environment, region) pair; the wrapper's job is only to:

1. resolve the **environment** (flag > git branch > error),
2. load its **YAML config** (regions, primary region, account/stage),
3. expand the requested **regions** in the right order,
4. run `cdk <verb>` with the correct env vars, `--context`, and stack selectors — echoing the
   full command line before running it, so users always see and can reproduce the raw CDK call.

No state, no lockfiles, no template post-processing. If `cdkw` disappears tomorrow, the echoed
commands are the migration path back to plain CDK.

## CLI surface

```
cdkw <verb> [ENVIRONMENT] [--region REGION]... [--all-regions] [-- <extra cdk args>]
```

- **Verbs**: `synth`, `diff`, `deploy`, `destroy`, `list` — 1:1 with CDK. Unknown trailing args
  after `--` pass through to `cdk` untouched (e.g. `--require-approval never`, `--exclusively`).
- **`ENVIRONMENT`** (optional positional): e.g. `test-main`, `stage-nft`, `feature-123`. When
  omitted, derived from the git branch (`feature/ABC-123-some-test` → `feature-123`); error out
  with the list of known environments if neither works.
- **`--region` / `-r`** (repeatable): target one or more specific regions, run **in the given
  order**. Must be in the environment's configured region list, else error.
- **`--all-regions`**: iterate all configured regions, **primary region first** (for `destroy`:
  primary **last**). Default when no `--region` is given for `synth`/`diff`/`list`; for
  `deploy`/`destroy` a region must be chosen explicitly or confirmed interactively — granular
  one-region-at-a-time control is the core requirement, so mutating verbs never fan out silently.
- **`--dry-run`**: print the composed `cdk` commands without executing.

Examples:

```sh
cdkw diff                                  # env from branch, all its regions
cdkw deploy test-main -r us-east-1         # one env, one region
cdkw deploy test-main -r us-east-1 -r us-west-1   # explicit sequence
cdkw deploy stage-nft --all-regions        # primary first, then the rest
cdkw destroy feature-123 --all-regions     # reverse order: primary last
cdkw deploy prod-main -r eu-central-1 -- --require-approval never
```

## Environment resolution

1. Explicit positional argument wins.
2. Otherwise parse the git branch: `feature/<TICKET>-<slug>` → `feature-<ticket number>`
   (e.g. `feature/ABC-123-some-test` → `feature-123`). The regex lives in one place and is
   configurable per project (see project config below).
3. Otherwise fail with a clear message listing environments found in the config directory.

Stage (account) is a *property of* the environment config, never inferred: mapping `feature-*` →
test account etc. is data, not code.

## Configuration

### Per-environment YAML (`config/<environment>.yml`) — already exists

```yaml
# config/stage-nft.yml
stage: stage                # test | stage | prod → selects the AWS account
account: "222222222222"     # or resolved from a stage→account map in project config
regions: # deployment targets, the single source of truth
  - us-east-1
  - eu-central-1
primary_region: us-east-1   # optional; provides global resources, deployed first
# ... arbitrary app-specific values, passed through to app.py untouched
```

Feature environments share `config/dev-feature.yml`; the wrapper instantiates it per feature by
substituting the resolved environment name (config file lookup: exact name first, then the
feature fallback).

### Project config (`cdkw.yml`, repo root)

Small and optional-by-default:

```yaml
config_dir: config
app_dir: .                  # where cdk.json lives
branch_pattern: 'feature/[A-Za-z]+-(?P<num>\d+).*'   # → feature-<num>
env_context_key: stage      # produces: --context stage=<environment>
stack_pattern: '{environment}-{region}/*'            # cdk stack selector template
accounts: # stage → account map (if not in each env file)
  test: "111111111111"
  stage: "222222222222"
  prod: "333333333333"
```

## Command composition

For each (environment, region) pair, in order, the wrapper runs:

```sh
CDK_DEPLOY_REGION=<region> \
cdk <verb> '<stack selector>' \
    --context stage=<environment> \
    --context region=<region> \
    <extra args>
```

- The environment reaches `app.py` via `--context` (matching the existing `--env stage=...`
  convention — the exact key is `env_context_key`). Region goes via context *and* env var so
  `app.py` can keep its current lookup.
- `app.py` remains the owner of stack construction: it reads the same YAML, synthesizes only the
  stacks for the requested (environment, region) — exactly as validated in the prototype's
  [`app.py`](prototype/app.cdk/app.py). The wrapper never parses templates.
- Stack selector comes from `stack_pattern`, so naming conventions stay in config.
- Regions run **sequentially**; a failure stops the sequence (later regions may depend on the
  primary region's global resources). `--continue-on-error` can be added later if needed.
- Exit code: the first failing `cdk` exit code, passed through unchanged.

## Ordering rules

| verb                    | default region order                                         |
|-------------------------|--------------------------------------------------------------|
| `synth`, `diff`, `list` | primary first, then config order                             |
| `deploy`                | primary first, then config order (only with `--all-regions`) |
| `destroy`               | reverse: config order reversed, primary **last**             |

## User experience & output design

The wrapper's terminal output should feel like a modern package manager (npm / pip / uv): a
clear **plan → progress → summary** arc, color and symbols for state, and raw tool output kept
visible but visually subordinate. Implemented with [rich](https://rich.readthedocs.io/)
(bundled by typer) — no extra dependency.

### 1. Run plan (before anything executes)

Every invocation starts by printing what was *resolved* and what *will run*, npm-style. This
doubles as the `--dry-run` output (dry-run stops here):

```
cdkw deploy stage-nft --all-regions

  environment  stage-nft            (explicit)
  stage        stage → 222222222222
  regions      us-east-1 ★, eu-central-1   (★ primary, deployed first)

  plan  2 × cdk deploy
    1. us-east-1     stage-nft-us-east-1/*
    2. eu-central-1  stage-nft-eu-central-1/*
```

When the environment came from the git branch, say so explicitly — silent inference is how
people deploy the wrong thing:

```
  environment  feature-123          (from branch feature/ABC-123-some-test)
```

For mutating verbs without `--region`/`--all-regions`, the interactive confirmation renders as
a checklist picker (arrow keys / space), not a y/N wall of text.

### 2. Per-region progress

Regions run sequentially, so render them as a task list that fills in as it goes — pip's
download style, one line per region, with a spinner on the active one and elapsed time on
completion:

```
  ✔ us-east-1     deploy   2m 41s
  ⠸ eu-central-1  deploy   0m 12s   CREATE_IN_PROGRESS  MyApp/Api/Handler
  ○ ap-south-1    queued
```

The `CREATE_IN_PROGRESS …` tail is opportunistic: parsed from CDK's own progress lines when
recognizable, blank otherwise — never blocking on parse success (see "stay close to CDK").

### 3. Raw CDK output: subordinate, not hidden

The echoed command line and CDK's own output stay fully visible (reproducibility is the core
promise), but styled to recede:

- The composed command is printed **bold** before each region run, prefixed with `$`, exactly
  copy-pasteable (env vars included).
- CDK stdout/stderr streams through live, dimmed and indented under the region's task line,
  prefixed with the region (`eu-central-1 │ …`) so interleaving stays legible in logs.
- `diff` output is the exception: it is the *product* of the command, so it passes through
  untouched and un-dimmed (CDK already colors it).

### 4. Summary

After the last region, an npm-audit-style one-glance summary with per-region timing and the
overall exit state:

```
  ── deploy stage-nft ──────────────────────────
  ✔ us-east-1      2m 41s
  ✖ eu-central-1   0m 58s   exit 1 — sequence stopped
  ○ ap-south-1     skipped

  1 succeeded · 1 failed · 1 skipped        3m 39s
```

On failure, the summary repeats the failing region's composed command line so the user can
rerun just that region without scrolling back.

### 5. Degradation rules

- **No TTY** (CI, piped): no spinners, no colors, no interactive picker — plain sequential
  logs with the same information (plan block, `$ cmd`, prefixed output, summary). Rich
  handles detection; `--plain` / `NO_COLOR` force it.
- **`--quiet`**: suppress the plan block and dimmed CDK output; keep commands, errors, summary.
- Interactive prompts never appear without a TTY — missing region selection in CI is a hard
  error with a hint (`pass --region or --all-regions`).
- All decoration goes to **stderr**; stdout carries only pass-through CDK output (so
  `cdkw synth` / `cdkw diff` stay pipeable).

## Implementation notes

- **Language/stack**: Python ≥3.12, [typer](https://typer.tiangolo.com/) for the CLI, `pyyaml`,
  `subprocess.run` shelling out to the `cdk` CLI (npm-installed, local dep preferred). No CDK
  Toolkit Library — it is TypeScript-only (see RESEARCH.md).
- **Windows-safe**: invoke `cdk` via its resolved `.cmd` shim / `npx.cmd`; never rely on bare
  `python` in `cdk.json` (prototype lesson: use an explicit interpreter path).
- **Testing**: unit-test environment resolution, region ordering, and command composition as pure
  functions (given config + args → list of command lines). Integration = `--dry-run` snapshot
  tests; no AWS needed.
- **Packaging**: single package `cdkw`, installable with `uv tool install` / `pipx`; entry point
  `cdkw`.
- **TUI (later, optional)**: an interactive picker (environment → region checklist → verb) on top
  of the same composition core, e.g. with textual. Not in scope for v1 — the CLI must be complete
  and scriptable first.

## Out of scope (v1)

- Credential/profile management — users bring their own `AWS_PROFILE`/SSO session; the wrapper
  only *checks* that the resolved account matches `cdk`'s target and fails fast on mismatch
  (nice-to-have, not required for v1).
- Cross-environment orchestration (deploy several environments in one run).
- Parallel region deploys — sequential is a feature (primary-first ordering).
- Bootstrapping (`cdk bootstrap`) — can be run manually; may become a verb later.
