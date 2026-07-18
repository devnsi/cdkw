# Possible Ideas

Evaluated against [DESIGN.md](DESIGN.md). Guiding lens: the tool is a *command composer* — no
state, no abstraction layer; every idea must keep the echoed-`cdk`-command migration path intact.

## Interactive require-approval

Today CDK's own security-diff approval prompt runs inside the dimmed, region-prefixed stream
(runner pipes stdout/stderr), which likely breaks or buries it; the workaround is
`-- --require-approval never`.

- **Pros**: Fixes a real UX hazard for `deploy` — a hidden prompt looks like a hang; a
  wrapper-level confirmation matches the existing questionary picker style.
- **Cons**: Intercepting/answering CDK's prompt means parsing its output — against "never
  blocking on parse success"; replacing it with `--require-approval never` plus a wrapper prompt
  changes security semantics (the wrapper would have to show the security diff itself).
- **Approach**: Cheapest correct fix: for `deploy`/`destroy` on a TTY, don't pipe — hand the
  child the real stdin/stdout for the approval-capable verbs (losing the dimmed prefix for those
  runs), or explicitly document/require `--require-approval` passthrough and detect a stalled
  child as a hint. Avoid re-implementing the approval flow — **solve as an I/O plumbing fix, not
  a feature**.

## Stack selection

Target a subset of stacks within a region, e.g. `cdkw deploy -s Api`.

- **Pros**: CDK supports it natively (positional selectors + `--exclusively`); today the wrapper
  always emits `{environment}-{region_short}/*` and passthrough args can't replace that
  positional, so users have no way to narrow.
- **Cons**: Another axis of selection on top of environment × region; wildcard/naming rules leak
  into the wrapper's UX.
- **Approach**: Add repeatable `--stack/-s NAME`; compose the selector as
  `{environment}-{region_short}/<NAME>` per value instead of `/*` (keep `stack_pattern`'s prefix
  logic — replace only the trailing segment, or add a `stack_pattern` variant key like
  `stack_selector: '{environment}-{region_short}/{stack}'`). Pure composition change, dry-run
  snapshot tests. **Good fit** — it's still just command composition.

## Regionless environments (local / no region)

For running `deploy`/`diff`/etc. against e.g. localstack — but **not** as a special case: all
localstack redirection (endpoints, fake accounts) lives in the app-specific YAML values and
`app.py`, never in cdkw. The wrapper only makes the region dimension optional, so the template
renders per *environment* alone.

- **Pros**: No localstack knowledge in the wrapper; falls out of the existing model as "an
  environment whose unit count is one"; keeps the stack pattern convention configurable.
- **Cons**: Second selector template to maintain; app and wrapper must agree on the region-less
  stage naming (same pinned-by-test discipline as `region_short`); touches CLI validation,
  composition, and the picker.
- **Sketch**:
    - Empty/omitted `regions` map in the environment YAML ⇒ regionless.
    - Exactly one composed command; no `--context region=...`; `--region`/`--all-regions` are
      errors; mutating verbs skip the interactive picker (the single unit is the granular unit);
      ordering rules don't apply.
    - Selector from a new `stack_pattern_regionless` key (default `{environment}/*`;
      `{region}`/`{region_short}` invalid there); app creates one stage named without a region
      suffix.
