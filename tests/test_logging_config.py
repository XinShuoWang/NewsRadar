import logging

from newsradar.logging import TRACE_LEVEL, configure_logging, parse_log_level


def test_parse_log_level_supports_trace_debug_info_warning_error():
    assert parse_log_level("TRACE") == TRACE_LEVEL
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level("INFO") == logging.INFO
    assert parse_log_level("warning") == logging.WARNING
    assert parse_log_level("ERROR") == logging.ERROR


def test_parse_log_level_rejects_unknown_level():
    try:
        parse_log_level("verbose")
    except ValueError as exc:
        assert str(exc) == "unsupported_log_level:verbose"
    else:
        raise AssertionError("parse_log_level should reject unsupported levels")


def test_configure_logging_registers_trace_method():
    configure_logging("TRACE", force=True)
    logger = logging.getLogger("newsradar.test")

    assert logging.getLevelName(TRACE_LEVEL) == "TRACE"
    assert logger.isEnabledFor(TRACE_LEVEL)
    assert callable(getattr(logger, "trace"))
