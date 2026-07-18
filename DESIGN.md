# Design: `cdkw` — a thin CDK wrapper CLI

Design for the custom Python CLI. Background, terminology, and usage live in the
[README](README.md); the conventions below are validated by the runnable example app in
[`workspace/`](workspace/README.md), which is the reference the wrapper must drive.

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

- **Verbs**: `synth`, `diff`, `deploy`, `destroy`, `list`, `watch` — 1:1 with CDK. Unknown trailing args
  after `--` pass through to `cdk` untouched (e.g. `--require-approval never`, `--exclusively`).
- **`ENVIRONMENT`** (optional positional): e.g. `test-main`, `stage-nft`, `feature-123`. When
  omitted, derived from the git branch (`feature/ABC-123-some-test` → `feature-123`); error out
  with the list of known environments if neither works.
- **`--region` / `-r`** (repeatable): target one or more specific regions, run **in the given
  order**. Accepts the full region name (`us-east-1`) or its `region_short` code (`use1`); short
  input requires the environment's shortcodes to be collision-free (the same rule `stack_pattern`
  enforces). Must resolve to the environment's configured region list, else error listing both
  forms.
- **`--all-regions`**: iterate all configured regions, **primary region first** (for `destroy`:
  primary **last**). Default when no `--region` is given for `synth`/`diff`/`list`; for
  `deploy`/`destroy`/`watch` a region must be chosen explicitly or confirmed interactively —
  granular one-region-at-a-time control is the core requirement, so mutating verbs never fan out
  silently. `watch` runs until interrupted, so it targets exactly **one** region: `--all-regions`
  and multiple `--region` values are errors, and the interactive prompt is a single pick.
- **`--dry-run`**: print the composed `cdk` commands without executing.

Worked examples for each of these are in the [README](README.md#usage).

## Environment resolution

1. Explicit positional argument wins.
2. Otherwise parse the git branch: `feature/<TICKET>-<slug>` → `feature-<ticket number>`
   (e.g. `feature/ABC-123-some-test` → `feature-123`). The regex lives in one place and is
   configurable per project (see project config below).
3. Otherwise fail with a clear message listing environments found in the config directory.

Stage (account) is a *property of* the environment config, never inferred: mapping `feature-*` →
test account etc. is data, not code.

## Configuration

### Per-environment YAML (`environments/<environment>.yaml`) — already exists

Schema as implemented and validated in
[`workspace/src/config/environment.py`](workspace/src/config/environment.py) (pydantic model):

```yaml
# environments/stage-nft.yaml
account: "222222222222"     # AWS account of the stage
profile: "account-stage"    # optional; AWS profile to use for this account
stage: stage                # test | stage | prod

regions: # deployment targets, the single source of truth (map, not list)
  us-east-1:
    is_primary: true        # provides global resources, deployed first
  eu-central-1:
    is_primary: false
# ... arbitrary app-specific values, passed through to app.py untouched
```

The primary region is the entry with `is_primary: true` (derived property, not a separate key);
region order otherwise follows the map's declaration order. Feature environments share
[`environments/dev-feature.yaml`](workspace/environments/dev-feature.yaml); config file lookup
is exact name first (`environments/<env>.yaml`), then `feature-*` names fall back to the shared
file. Unknown environments fail with a message listing the known ones — the wrapper reuses this
loader (or mirrors it exactly) rather than inventing a second schema.

### Project config (`cdkw.yml`, repo root)

Small and optional-by-default; defaults match the workspace conventions:

```yaml
config_dir: environments
app_dir: .                  # where cdk.json lives
branch_pattern: 'feature/[A-Za-z]+-(?P<num>\d+).*'   # → feature-<num>
env_context_key: env        # produces: --context env=<environment>
stack_pattern: '{environment}-{region_short}/*'      # cdk stack selector template
feature_fallback: dev-feature                        # shared config for feature-* envs

hooks:                      # optional; shell commands run around each composed cdk command
  pre: 'uv run scripts/prepare.py'
  post: 'uv run scripts/tag_deployment.py'
```

Accounts and profiles live in each environment file (no stage→account map needed).

`stack_pattern` may use `{environment}`, `{region}` (full name), and `{region_short}` — an
abbreviated region derived by `cdkw.resolve.region_short`: prefix and trailing number kept,
each middle word contributing its first letter, compound directions two (`us-east-1` → `use1`,
`ap-south-1` → `aps1`, `ap-southeast-1` → `apse1`, `us-gov-west-1` → `usgw1`). The wrapper
refuses to compose commands when two configured regions would collide on a shortcode.

## Command composition

For each (environment, region) pair, in order, the wrapper runs:

```sh
cdk <verb> '<environment>-<region_short>/*' \
    --context env=<environment> \
    --context region=<region> \
    --profile <profile> \
    <extra args>
```

- The environment reaches `app.py` via `--context env=...` (key configurable as
  `env_context_key`). Region also goes via context; `app.py` additionally honors
  `CDK_DEPLOY_REGION`, but context wins, so the wrapper only sets the context.
- `--profile` is added when the environment config specifies one; otherwise the ambient
  credentials apply.
- `app.py` remains the owner of stack construction: it reads the same YAML and creates one
  `cdk.Stage` named `<environment>-<region_short>` per configured region, narrowing to the single
  requested region when the `region` context is set — exactly as validated in
  [`workspace/src/app.py`](workspace/src/app.py). It also validates that the requested region
  is configured for the environment, so wrapper and app agree on errors. The wrapper never
  parses templates.
- Stack selector comes from `stack_pattern` (default `{environment}-{region_short}/*`, matching
  the workspace's stage naming), so naming conventions stay in config. The app's stage ids must
  be derived with the same `region_short` rule — the workspace keeps its copy in
  [`workspace/src/config/environment.py`](workspace/src/config/environment.py), pinned to the
  wrapper's by a test.
- Regions run **sequentially**; a failure stops the sequence (later regions may depend on the
  primary region's global resources). `--continue-on-error` can be added later if needed.
- Exit code: the first failing `cdk` exit code, passed through unchanged.

## Hooks

`cdkw` stays a command composer; everything else is an **extension point**: two user-provided
shell commands, `pre` and `post`, declared in `cdkw.yml` and run around each composed cdk
command. Hooks that only care about some verbs branch on `CDKW_VERB` themselves — deliberately
no per-verb keys. Example uses: git deployment tags (`post` tagging
`env/$CDKW_ENVIRONMENT-$CDKW_REGION_SHORT` on deploy, removing it on destroy), notifications,
or a `pre` hook that (re)generates environment YAMLs — the wrapper still reads only the YAML,
so the single source of truth stands.

- Hooks run **once per composed command** (per environment × region unit), from the **repo
  root**, through the platform shell (`shell=True`: cmd.exe on Windows, `/bin/sh` on POSIX).
- Context via environment variables (merged over the ambient environment): `CDKW_VERB`,
  `CDKW_ENVIRONMENT`, `CDKW_STAGE`, `CDKW_ACCOUNT`, `CDKW_PROFILE` (empty when unset),
  `CDKW_REGION`, `CDKW_REGION_SHORT`; the post hook additionally gets `CDKW_EXIT_CODE`.
- **Env injection (pre → cdk)**: the pre hook receives `CDKW_ENV`, the path of a fresh temp
  file; `KEY=VALUE` lines it writes there (blanks and `#` comments ignored, malformed lines
  warn and are skipped) are merged into that unit's cdk child environment — GitHub-Actions
  `$GITHUB_ENV` style, so hook *stdout* stays unparsed. Injected vars are echoed dimmed
  (`env KEY=VALUE`) above the cdk command so the run stays reproducible by hand.
- **Failure semantics**: a failing `pre` hook fails the unit with the hook's exit code — the
  cdk command does not run and the sequence stops, exactly like a failing cdk command. The
  `post` hook fires **regardless of the cdk exit code** (compensating actions), but never for
  skipped units; a failing post hook is a warning (immediate and in the summary) and leaves
  the run's exit code unchanged.
- Hooks are echoed `$`-prefixed with a dim `(pre hook)` / `(post hook)` annotation and appear
  in `--dry-run` output; their output streams dimmed/region-prefixed like cdk's. The wrapper
  never parses hook stdout and never reads back anything except the `CDKW_ENV` file — hooks
  are side effects, not state.

## Ordering rules

"Config order" is the declaration order of the `regions` map in the environment YAML.

| verb                    | default region order                                         |
|-------------------------|--------------------------------------------------------------|
| `synth`, `diff`, `list` | primary first, then config order                             |
| `deploy`                | primary first, then config order (only with `--all-regions`) |
| `destroy`               | reverse: config order reversed, primary **last**             |
| `watch`                 | exactly one region (explicit `--region` or interactive pick) |

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

  environment  stage-nft                   (explicit)
  stage        stage → 222222222222
  regions      us-east-1 ★, eu-central-1   (★ primary, deployed first)

  plan  2 × cdk deploy
    1. us-east-1     stage-nft-use1/*
    2. eu-central-1  stage-nft-euc1/*
```

When the environment came from the git branch, say so explicitly — silent inference is how
people deploy the wrong thing:

```
  environment  feature-123                 (from branch feature/ABC-123-some-test)
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
  copy-pasteable.
- CDK stdout/stderr streams through live, dimmed and indented under the region's task line,
  prefixed with the region (`eu-central-1 │ …`) so interleaving stays legible in logs.
- `diff` output is the exception: it is the *product* of the command, so it passes through
  untouched and un-dimmed. Because the child runs behind pipes, the wrapper sets
  `FORCE_COLOR=1` for `diff` (only when on a TTY, and never under `--plain`/`NO_COLOR`) so
  CDK's green/red resource markers survive.

### 4. Summary

After the last region, a npm-audit-style one-glance summary with per-region timing and the
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

- **Language/stack**: Python ≥3.14 managed with uv (matching the workspace),
  [typer](https://typer.tiangolo.com/) for the CLI, `pyyaml` + `pydantic` for config (same
  models as the workspace's `EnvironmentConfig`), `subprocess.run` shelling out to the `cdk`
  CLI via `npx cdk` (npm dependency, no global install). No CDK Toolkit Library — it is
  TypeScript-only (see RESEARCH.md).
- **Windows-safe**: invoke `cdk` via its resolved `.cmd` shim / `npx.cmd`; never rely on bare
  `python` in `cdk.json` — the workspace's `cdk.json` uses `uv run python -m src.app` as the
  explicit interpreter. The wrapper must key success off the exit code, not the presence of
  stderr noise (see the jsii `ENOTEMPTY` quirk in [workspace/README.md](workspace/README.md)).
- **Testing**: unit-test environment resolution, region ordering, and command composition as pure
  functions (given config + args → list of command lines). Integration = `--dry-run` snapshot
  tests; no AWS needed.
- **Packaging**: single package `cdkw`, installable with `uv tool install` / `pipx`; entry point
  `cdkw`.

## Out of scope

- Credential management — the wrapper passes the environment's configured `profile` as
  `--profile` but does not log in or refresh SSO sessions; users bring their own. Checking that
  the resolved account matches `cdk`'s target and failing fast on mismatch is a nice-to-have,
  not required for v1.
- Cross-environment orchestration (deploy several environments in one run).
- Built-in deployment tagging, notifications, or config generation — these are user
  [hooks](#hooks), never wrapper features.
- Parallel region deploys — sequential is a feature (primary-first ordering).
- Bootstrapping (`cdk bootstrap`) — can be run manually; may become a verb later.
