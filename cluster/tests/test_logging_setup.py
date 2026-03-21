"""Tests for shared.logging_setup — structured logging configuration."""
import logging

import pytest
import structlog

from shared.logging_setup import setup_logging, request_id_var, _configured
import shared.logging_setup as logging_mod


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset the logging module state before each test."""
    logging_mod._configured = False
    yield
    logging_mod._configured = False


class TestSetupLogging:
    def test_idempotent(self):
        """Calling setup_logging twice doesn't raise or re-configure."""
        setup_logging(json_output=False)
        assert logging_mod._configured is True
        # Second call is a no-op
        setup_logging(json_output=False)
        assert logging_mod._configured is True

    def test_sets_configured_flag(self):
        assert logging_mod._configured is False
        setup_logging(json_output=False)
        assert logging_mod._configured is True

    def test_structlog_configured(self):
        setup_logging(json_output=False)
        log = structlog.get_logger("test")
        # get_logger returns a lazy proxy; bind() resolves to the wrapper
        bound = log.bind(test_key="val")
        assert hasattr(bound, "info")
        assert hasattr(bound, "warning")

    def test_log_level_override(self):
        setup_logging(json_output=False, level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG


class TestRequestIdVar:
    def test_default_is_none(self):
        tok = request_id_var.set(None)
        assert request_id_var.get() is None
        request_id_var.reset(tok)

    def test_set_and_get(self):
        tok = request_id_var.set("abc123")
        assert request_id_var.get() == "abc123"
        request_id_var.reset(tok)
