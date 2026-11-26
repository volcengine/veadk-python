from veadk.utils import logger as logger_module


class _RaisingLogger:
    def info(self, message):
        raise RuntimeError("info failed")

    def warning(self, message):
        raise RuntimeError("warning failed")


def test_safe_info_swallows_logging_errors():
    logger_module.safe_info(_RaisingLogger(), "message")


def test_safe_warning_swallows_logging_errors():
    logger_module.safe_warning(_RaisingLogger(), "message")
