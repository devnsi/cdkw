"""Sample pre hook: prints the unit about to run (see DESIGN.md: Hooks for the CDKW_* vars)."""

import os

print(
    f"[pre] {os.environ['CDKW_VERB']} {os.environ['CDKW_ENVIRONMENT']} "
    f"in {os.environ['CDKW_REGION']} ({os.environ['CDKW_REGION_SHORT']}) "
    f"on stage {os.environ['CDKW_STAGE']} → {os.environ['CDKW_ACCOUNT']}"
)
