"""Application logs on stderr. Render keeps those lines. Do not log answer text or file bytes."""

from onb.log.record import configure, log_result, logger

__all__ = ["configure", "log_result", "logger"]
