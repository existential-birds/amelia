import logging
from backend.utils.logger import setup_logger


def test_setup_logger_returns_logger():
    """Test that setup_logger returns a logger instance"""
    logger = setup_logger("test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_logger_has_correct_level():
    """Test that logger has INFO level by default"""
    logger = setup_logger("test_logger")
    assert logger.level == logging.INFO


def test_logger_with_custom_level():
    """Test that logger respects custom log level"""
    logger = setup_logger("test_logger", level="DEBUG")
    assert logger.level == logging.DEBUG
