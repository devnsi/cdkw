# Sample post hook as a plain shell script — hooks are any shell command, not just Python.
# Fires on failure too; CDKW_EXIT_CODE tells it how the cdk command went.
echo "[post] $CDKW_VERB $CDKW_ENVIRONMENT in $CDKW_REGION finished with exit $CDKW_EXIT_CODE"
