import logging.config
import sys

def setup_logging(log_level: str = "INFO"):
    log_level = log_level.upper()
    
    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "json": {
                "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                # Include exc_info to capture full traceback in error logs
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d %(exc_info)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
            },
            "json": {
                "formatter": "json",
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
            },
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["default"],
                "level": log_level,
                "propagate": True,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": False,
            },
            "myapi": {
                "handlers": ["json"],
                "level": log_level,
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(LOGGING_CONFIG)
