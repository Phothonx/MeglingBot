import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "bot.log"

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the whole bot.

    Records go to the console and to a rotating file (``logs/bot.log``). Call
    this once at startup; modules then get their own logger via
    ``logging.getLogger(__name__)`` and inherit this configuration.
    """
    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Start from a clean slate so calling this twice doesn't duplicate output.
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Pycord is chatty at INFO (gateway, heartbeats); keep only its warnings.
    logging.getLogger("discord").setLevel(logging.WARNING)
