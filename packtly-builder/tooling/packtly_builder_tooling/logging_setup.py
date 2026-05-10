import json
import logging
import logging.config
from importlib import resources
from typing import Optional


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int | str) -> None:
        super().__init__()
        self.max_level = (
            logging.getLevelNamesMapping()[max_level.upper()]
            if isinstance(max_level, str)
            else max_level
        )

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


class LoggerManager:
    _configured: bool = False

    @staticmethod
    def setup() -> None:
        if LoggerManager._configured:
            return

        with resources.files(__package__).joinpath("logging.json").open("r") as f:
            config = json.load(f)

        # Important for pytest caplog and existing named loggers
        config.setdefault("disable_existing_loggers", False)

        logging.config.dictConfig(config)
        LoggerManager._configured = True

    @staticmethod
    def set_verbosity(verbosity: int) -> None:
        if not LoggerManager._configured:
            raise RuntimeError("LoggerManager must be set up before setting verbosity.")
        logging.getLogger().setLevel(verbosity)


def setup_logger(
    name: Optional[str] = None, verbosity: int = logging.INFO
) -> logging.Logger:
    LoggerManager.setup()
    LoggerManager.set_verbosity(verbosity)
    return logging.getLogger(name)


def set_verbosity(verbosity: int) -> None:
    LoggerManager.set_verbosity(verbosity)
