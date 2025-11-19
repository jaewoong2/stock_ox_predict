import logging.config
import sys

def setup_logging(log_level: str = "INFO"):
    log_level = log_level.upper()

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "\n{'=' * 80}\n%(asctime)s | %(levelname)-8s | %(name)s\n%(pathname)s:%(lineno)d\n%(message)s\n{'=' * 80}",
            },
            "simple": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
            },
        },
        "handlers": {
            "console": {
                "formatter": "simple",
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
            },
            "error_console": {
                "formatter": "detailed",
                "class": "logging.StreamHandler",
                "stream": sys.stderr,
                "level": "WARNING",
            },
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["console", "error_console"],
                "level": log_level,
                "propagate": True,
            },
            "uvicorn.error": {
                "handlers": ["console", "error_console"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "myapi": {
                "handlers": ["console", "error_console"],
                "level": log_level,
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(LOGGING_CONFIG)
