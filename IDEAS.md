# Possible Ideas

Evaluated against [DESIGN.md](DESIGN.md). Guiding lens: the tool is a *command composer* — no
state, no abstraction layer; every idea must keep the echoed-`cdk`-command migration path intact.

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
