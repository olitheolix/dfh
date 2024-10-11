import json
import logging
import sys

import dfh.logstreams

# Convenience.
logit = logging.getLogger("app")


class TestLogging:
    def test_basic(self):
        """Log messages for each level and one exception."""
        logit.debug("DEBUG hello-world")
        logit.debug("DEBUG hello-world", {"some": "data"})

        logit.info("INFO hello-world")
        logit.info("INFO hello-world", {"some": "data"})

        logit.warning("WARNING hello-world")
        logit.warning("WARNING hello-world", {"some": "data"})

        logit.error("ERROR hello-world")
        logit.error("ERROR hello-world", {"some": "data"})

        logit.critical("CRITICAL hello-world")
        logit.critical("CRITICAL hello-world", {"some": "data"})

        logit.exception("Something happened.")

    def test_setup_valid_log_levels(self):
        """Verify that all log levels are accepted."""
        # LUT for the numerical and human readable log levels.
        levels = [
            ("debug", 10),
            ("info", 20),
            ("warning", 30),
            ("error", 40),
            ("critical", 50),
        ]

        log_names = ["app", "fastapi", "uvicorn", "uvicorn.asgi", "asyncio"]

        # Configures the log stream and verify that each has exactly two
        # handlers, no matter how often they were initialised.
        for level_name, log_level_num in levels:
            # The setup must be idempotent. That is why we will configure them
            # several times and verify each time that all the log streams have
            # exactly one handler with that uses our custom JSON formatter.
            for _ in range(10):
                # Setup all log streams.
                assert dfh.logstreams.setup(level_name) is False

                # Verify that each log stream was setup correctly.
                for stream_name in log_names:
                    # Log stream must now exist.
                    assert stream_name in logging.root.manager.loggerDict

                    # Must have exactly one handler.
                    log = logging.getLogger(stream_name)
                    assert len(log.handlers) == 1

                    # The `asyncio` stream is locked to ERROR (level 40), but
                    # all others must have the desired log level.
                    if stream_name == "asyncio":
                        assert log.level == 40
                    else:
                        assert log.level == log_level_num

                    # Must be normal StreamHandler but use our custom JSON formatter.
                    handler = log.handlers[0]
                    assert isinstance(handler, logging.StreamHandler)
                    assert isinstance(handler.formatter, dfh.logstreams.JsonFormatter)

    def test_setup_invalid_log_levels(self):
        # Must return an error because the log level name is invalid.
        assert dfh.logstreams.setup("invalid-log-level-name") is True

    def test_formatter_basic(self):
        """Basic log command must produce valid JSON.

        Example: logit.info("msg")

        """
        formatter = dfh.logstreams.JsonFormatter()

        # A log record produced by eg `logit.info("msg")`
        record = logging.LogRecord(
            "name", 10, "path", 10, "msg", args=None, exc_info=None
        )
        log_line = json.loads(formatter.format(record))
        assert log_line == {
            "level": "DEBUG",
            "channel": "name",
            "line": "path:None:10",
            "message": "msg",
        }

    def test_formatter_extra(self):
        """Log command with extra data must produce valid JSON.

        Example: logit.info("msg", data={"foo": "bar"})

        """
        formatter = dfh.logstreams.JsonFormatter()

        # A log record produced by eg `logit.info("msg", extra={"foo": "bar"})`
        record = logging.LogRecord(
            "name",
            10,
            "path",
            10,
            "msg",
            args=[{"foo": "bar"}],  # type: ignore
            exc_info=None,  # type: ignore
        )
        log_line = json.loads(formatter.format(record))
        assert log_line == {
            "level": "DEBUG",
            "channel": "name",
            "line": "path:None:10",
            "message": "msg",
            "data": {"foo": "bar"},
        }

    def test_formatter_exception(self):
        """Log last exception.

        Example: logit.exception()

        """
        formatter = dfh.logstreams.JsonFormatter()
        kwargs = dict(
            name="name",
            level=10,
            pathname="path",
            lineno=2,
            msg="msg",
            args=[],
        )

        # A log record produced by eg `logit.info("msg")`. This one must not
        # contain an `exception` field in the JSON output.
        record = logging.LogRecord(**kwargs, exc_info=None)  # type: ignore
        log_line = json.loads(formatter.format(record))
        assert "exception" not in log_line

        # A log record produced by eg `logit.exception("msg")`. Unlike before,
        # this one must have an `exception` field in the JSON output.
        record = logging.LogRecord(**kwargs, exc_info=sys.exc_info())  # type: ignore
        log_line = json.loads(formatter.format(record))
        assert "exception" in log_line
