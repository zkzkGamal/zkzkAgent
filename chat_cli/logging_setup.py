"""Logging configuration — clean by default, verbose on demand."""

import logging
import sys
from datetime import datetime

from .ui import C, style

# The chatty internal agent loggers are muted to this level for a clean UI.
NOISY_LEVEL = logging.WARNING


class PrettyFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: C.GREY,
        logging.INFO: C.BLUE,
        logging.WARNING: C.YELLOW,
        logging.ERROR: C.RED,
        logging.CRITICAL: C.RED + C.BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        head = style(f"{ts} {record.levelname:<7}", color, C.DIM)
        return f"{head} {record.getMessage()}"


def configure_logging(verbose: bool, debug: bool) -> logging.Handler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(PrettyFormatter())

    root = logging.getLogger()
    # Wipe handlers other modules installed via logging.basicConfig(...).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)

    if debug:
        root.setLevel(logging.DEBUG)
    elif verbose:
        root.setLevel(logging.INFO)
    else:
        root.setLevel(NOISY_LEVEL)

    return handler


def set_level(level: int) -> None:
    logging.getLogger().setLevel(level)


def set_verbose(verbose: bool) -> None:
    set_level(logging.INFO if verbose else NOISY_LEVEL)
