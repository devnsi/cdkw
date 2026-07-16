# Tooling Research

Research (July 2026) into existing tools that could fill the requirements described in the
[README](README.md): granular multi-stage, multi-environment, multi-region CDK deployments driven
by per-environment YAML configs.

**Bottom line:** No off-the-shelf tool matches the requirements exactly. **Runway** comes
remarkably close and is worth evaluating first; everything else either solves a different problem
or is effectively dead.

## Closest fit: Runway

[Runway](https://github.com/onicagroup/runway) (originally Onica, now Rackspace) is a Python tool
that is almost a description of our README: a lightweight wrapper around deployment tools —
explicitly including AWS CDK — built to "ease management of per-environment configs & deployment."

- Per-environment configuration with deployments across multiple AWS accounts and regions.
- Derives the deploy environment from the git branch name (strips an `ENV-` prefix, e.g. branch
  `ENV-dev` → environment `dev`) — the same idea as our `feature/ABC-123-...` → `feature-123`
  convention, though the mapping rule differs and may need config or convention changes on our side.
- Distributed via PyPI (`pip install runway`); npm distribution was dropped.
- Caveat: Rackspace has kept it in
  ["mostly maintenance mode"](https://www.rackspace.com/blog/ready-for-lift-off-the-community-driven-future-of-runway)
  since the 2020 acquisition and is steering it toward community ownership — but it is not
  archived, and the latest release (v2.8.4) shipped July 2025 with ongoing commits.

## Second option: Sceptre (+ sceptre-cdk-handler)

[Sceptre](https://github.com/Sceptre/sceptre) is a mature, actively maintained Python
CloudFormation orchestrator whose core model matches ours: a directory tree of per-environment
YAML config files reusing common templates, plus hooks, resolvers, and cross-stack output wiring.

The catch is CDK support: the
[sceptre-cdk-handler](https://github.com/sceptre/sceptre-cdk-handler) lets Sceptre synthesize
Python CDK stack classes and deploy them itself (bypassing `cdk deploy` entirely), but it is a
young plugin with ~13 commits and minimal activity — adopting it means betting on a thin,
barely-maintained bridge and restructuring the existing `app.py` into Sceptre's stack-class model.

## CDK-native options (solve a different problem)

- **CDK Stages + context/YAML config**: our per-environment YAML approach is a recognized pattern
  ([Xebia's writeup](https://xebia.com/blog/managing-multiple-environments-in-the-aws-cdk-using-yaml-configuration-files/),
  [rehanvdm's "4 methods"](https://rehanvdm.com/blog/4-methods-to-configure-multiple-environments-in-the-aws-cdk)) —
  but native CDK still leaves us composing `cdk deploy 'Env/Region/*' --context ...` commands by
  hand, which is exactly the combinatorial pain the justfiles had.
- **[CDK Pipelines](https://docs.aws.amazon.com/cdk/v2/guide/cdk-pipeline.html)** and
  **[cdk-express-pipeline](https://rehanvdm.com/blog/migrate-from-cdk-pipelines-to-cdk-express-pipeline)**:
  these orchestrate multi-account/multi-region *CI/CD* rollouts. Good for the `*-main`
  environments' promotion flow, but not for the interactive "deploy this environment to this
  region now" developer workflow we want.
- **[CDK Toolkit Library](https://docs.aws.amazon.com/cdk/v2/guide/toolkit-library.html)**
  (`@aws-cdk/toolkit-lib`): the official programmatic API for synth/diff/deploy — the right
  foundation *if we build our own wrapper* — but it is TypeScript/Node only. It can drive a Python
  `app.py` as its cloud-assembly source, but the wrapper CLI itself would have to be TS. A Python
  wrapper would instead shell out to the `cdk` CLI (which is what Runway does).

## Not viable

- **[Stacker](https://github.com/cloudtools/stacker)**: archived/unmaintained; troposphere-based,
  pre-dates CDK.
- **Terragrunt**: the conceptual model we want (thin DRY wrapper, per-env config tree, granular
  unit deploys) but it only wraps Terraform/OpenTofu, not CDK.

## Prototype results (2026-07-16)

A working Runway prototype lives in [`prototype/`](prototype/README.md) — branch-based environment
resolution, per-(environment, region) CDK invocations, and per-env YAML region filtering all work.
But the friction points predicted below were confirmed: regions are declared per deployment block
(not per environment), single-region targeting from the CLI is not first-class, and our branch
naming convention needs a shim. See the prototype README for details. A `deploy` round-trip with
real AWS credentials is still outstanding.

## Recommendation

Prototype with **Runway** first — point it at one environment YAML and the existing `app.py` and
see whether its environment/region model and branch-derivation rules bend to our conventions. The
likely friction points are its `ENV-` branch-name convention and whether its region handling gives
the granular one-region-at-a-time sequencing (with primary-region-first) we need.

If it can't, the research supports the fallback plan: a small custom Python CLI (typer/click) that
reads the YAML files, resolves the environment from the branch, and shells out to
`cdk synth/diff/deploy/destroy` with the right `--context`/`--env` and stack selectors — none of
the existing tools would save much effort over that.

## Sources

- [Runway GitHub](https://github.com/onicagroup/runway)
- [Runway docs](https://docs.onica.com/projects/runway/en/stable/commands.html)
- [Rackspace on Runway's future](https://www.rackspace.com/blog/ready-for-lift-off-the-community-driven-future-of-runway)
- [Sceptre](https://github.com/Sceptre/sceptre)
- [sceptre-cdk-handler](https://github.com/sceptre/sceptre-cdk-handler)
- [CDK environments docs](https://docs.aws.amazon.com/cdk/v2/guide/environments.html)
- [CDK Pipelines](https://docs.aws.amazon.com/cdk/v2/guide/cdk-pipeline.html)
- [cdk-express-pipeline migration](https://rehanvdm.com/blog/migrate-from-cdk-pipelines-to-cdk-express-pipeline)
- [CDK Toolkit Library](https://docs.aws.amazon.com/cdk/v2/guide/toolkit-library.html)
- [Xebia: YAML multi-env CDK](https://xebia.com/blog/managing-multiple-environments-in-the-aws-cdk-using-yaml-configuration-files/)
- [4 methods to configure multiple environments](https://rehanvdm.com/blog/4-methods-to-configure-multiple-environments-in-the-aws-cdk)
- [Stacker](https://github.com/cloudtools/stacker)
