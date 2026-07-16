class CdkwError(Exception):
    """User-facing error; the CLI prints the message and exits with `exit_code`."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code
