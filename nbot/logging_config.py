"""Process-level logging defaults."""

from collections.abc import MutableMapping, Sequence


def configure_ncatbot_log_file_name(
    argv: Sequence[str],
    environ: MutableMapping[str, str],
) -> None:
    """Give standalone MCP its own ncatbot log file on Windows.

    ncatbot uses TimedRotatingFileHandler. Two independent processes cannot
    rotate the same file safely on Windows, so keep the default bot log name
    for the main process and split mcp-only into a separate file.
    """
    if environ.get("LOG_FILE_NAME"):
        return

    if "--mcp-only" in argv:
        environ["LOG_FILE_NAME"] = "mcp_%Y_%m_%d.log"
    else:
        environ["LOG_FILE_NAME"] = "bot_%Y_%m_%d.log"
