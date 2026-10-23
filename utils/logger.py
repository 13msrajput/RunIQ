"""Project-wide logging helper (console + rotating file)."""

from __future__ import annotations

import logging  # standard library logging
from logging.handlers import RotatingFileHandler  # keeps log files small

_CONFIGURED = False  # make sure handlers are attached only once


def _configure_root() -> None:
    """Attach console and file handlers to the "runiq" logger (once)."""
    global _CONFIGURED  # module level flag
    if _CONFIGURED:  # Streamlit re-runs scripts; avoid duplicate handlers
        return
    from config import get_settings  # imported lazily to avoid circular imports

    settings = get_settings()  # read log level + directory
    root = logging.getLogger("runiq")  # parent of all project loggers
    root.setLevel(getattr(logging, settings.log_level, logging.INFO))  # apply level
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )  # log layout
    console = logging.StreamHandler()  # print to the terminal
    console.setFormatter(formatter)  # apply layout
    root.addHandler(console)  # register console handler
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)  # create logs/ folder
        file_handler = RotatingFileHandler(
            settings.log_dir / "app.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)  # apply layout
        root.addHandler(file_handler)  # register file handler
    except OSError:  # read-only file system (e.g. some cloud hosts)
        root.warning("File logging disabled: cannot write to %s", settings.log_dir)
    root.propagate = False  # do not duplicate messages in the root logger
    _CONFIGURED = True  # mark done


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger called ``cricbuzz.<name>``."""
    _configure_root()  # make sure handlers exist
    return logging.getLogger(f"runiq.{name}")  # namespaced logger
