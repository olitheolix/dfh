"""Configure streams to emit JSON strings."""

import json
import logging


class JsonFormatter(logging.Formatter):
    """Return log record as JSON string."""

    def format(self, record: logging.LogRecord) -> str:
        # Compile the log message in the desired JSON format.
        msg = {
            "level": f"{record.levelname}",
            "channel": f"{record.name}",
            "line": f"{record.filename}:{record.funcName}:{record.lineno}",
            "message": record.msg,
        }

        # Add a "data" field if the user provided extra arguments to the log
        # call, eg `log.info("foo", extra={'x': 'y'})`.
        if record.args:
            msg["data"] = record.args  # type: ignore

        # If this was an exception, ie `log.exception()`, then use the built in
        # exception formatter.
        if record.exc_info:
            msg["exception"] = self.formatException(record.exc_info)

        return json.dumps(msg)


def setup(level: str) -> bool:
    """Configure all log streams with `level`.

    Valid levels: "debug", "info", "warning", "error".

    The level names are not case-sensitive.

    """
    # Sanity check.
    level = level.upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return True

    # Create a StreamHandler instance with our JSON formatter.
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    # Configure the typical log streams of any FastAPI application.
    logger_names = ["app", "fastapi", "uvicorn", "uvicorn.asgi", "asyncio"]
    for name in logger_names:
        # Flush any existing handler and install our own.
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(handler)

        # Set the `level` as specified by the user. The only exception is
        # `asyncio` because it creates a lot of useless noise below ERROR.
        if name == "asyncio":
            logger.setLevel(logging.ERROR)
        else:
            logger.setLevel(level)

        # Emit debug log message.
        logger.debug(f"Set log level for {name} logger to {level}")

    # Setup successful.
    return False
