import pytest
import logging
from packtly_builder_tooling.logging_setup import (
    MaxLevelFilter,
    setup_logger,
    set_verbosity,
)


@pytest.fixture()
def loggerObj() -> logging.Logger:
    return setup_logger("logger")


def test_debug_logged(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    test_msg = "debug-message"
    with caplog.at_level(logging.DEBUG):
        loggerObj.debug(test_msg)
    assert any(
        record.levelname == "DEBUG" and record.message == test_msg
        for record in caplog.records
    )


def test_info_logged(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    test_msg = "info-message"
    with caplog.at_level(logging.DEBUG):
        loggerObj.info(test_msg)
    assert any(
        record.levelname == "INFO" and record.message == test_msg
        for record in caplog.records
    )


def test_warning_logged(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    test_msg = "warning-message"
    with caplog.at_level(logging.DEBUG):
        loggerObj.warning(test_msg)
    assert any(
        record.levelname == "WARNING" and record.message == test_msg
        for record in caplog.records
    )


def test_critical_logged(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    test_msg = "critical-message"
    with caplog.at_level(logging.DEBUG):
        loggerObj.critical(test_msg)
    assert any(
        record.levelname == "CRITICAL" and record.message == test_msg
        for record in caplog.records
    )


def test_max_level_filter_accepts_info() -> None:
    flt = MaxLevelFilter("INFO")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="info",
        args=(),
        exc_info=None,
    )
    assert flt.filter(record) is True


def test_max_level_filter_rejects_warning() -> None:
    flt = MaxLevelFilter("INFO")
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="warn",
        args=(),
        exc_info=None,
    )
    assert flt.filter(record) is False


def test_handler_wiring_uses_max_level_filter(loggerObj: logging.Logger) -> None:
    root = logging.getLogger()
    handlers = root.handlers

    stdout_like_handlers = [
        h for h in handlers if any(isinstance(f, MaxLevelFilter) for f in h.filters)
    ]
    stderr_like_handlers = [h for h in handlers if h.level == logging.WARNING]

    assert len(stdout_like_handlers) == 1
    assert len(stderr_like_handlers) == 1

    stdout_handler = stdout_like_handlers[0]
    stderr_handler = stderr_like_handlers[0]

    assert any(isinstance(f, MaxLevelFilter) for f in stdout_handler.filters)
    assert stderr_handler.level == logging.WARNING


def test_stream_routing_with_caplog(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    with caplog.at_level(logging.DEBUG):
        loggerObj.debug("capture-debug")
        loggerObj.info("capture-info")
        loggerObj.warning("capture-warning")
        loggerObj.error("capture-error")

    levels = [r.levelname for r in caplog.records]

    assert "DEBUG" in levels
    assert "INFO" in levels
    assert "WARNING" in levels
    assert "ERROR" in levels

    # Verify MaxLevelFilter blocks WARNING+ from stdout handler
    root = logging.getLogger()
    stdout_handler = next(
        h
        for h in root.handlers
        if any(isinstance(f, MaxLevelFilter) for f in h.filters)
    )
    flt = next(f for f in stdout_handler.filters if isinstance(f, MaxLevelFilter))
    assert flt.filter(caplog.records[1]) is True  # INFO passes
    assert flt.filter(caplog.records[2]) is False  # WARNING blocked


def test_debug_suppressed_at_info_verbosity(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    """When verbosity=INFO, DEBUG messages must not be logged."""
    set_verbosity(logging.INFO)

    with caplog.at_level(logging.INFO):
        loggerObj.debug("should-not-appear")
        loggerObj.info("should-appear")

    levels = [r.levelname for r in caplog.records]
    assert "DEBUG" not in levels
    assert "INFO" in levels


def test_debug_visible_at_debug_verbosity(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    """When verbosity=DEBUG, DEBUG messages must be logged."""
    set_verbosity(logging.DEBUG)

    with caplog.at_level(logging.DEBUG):
        loggerObj.debug("should-appear")
        loggerObj.info("also-appears")

    levels = [r.levelname for r in caplog.records]
    assert "DEBUG" in levels
    assert "INFO" in levels


def test_warning_suppressed_at_warning_verbosity(
    caplog: pytest.LogCaptureFixture, loggerObj: logging.Logger
) -> None:
    """When verbosity=WARNING, INFO and DEBUG must not be logged."""
    set_verbosity(logging.WARNING)

    with caplog.at_level(logging.WARNING):
        loggerObj.debug("hidden")
        loggerObj.info("hidden")
        loggerObj.warning("visible")

    levels = [r.levelname for r in caplog.records]
    assert "DEBUG" not in levels
    assert "INFO" not in levels
    assert "WARNING" in levels
