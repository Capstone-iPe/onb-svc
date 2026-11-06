"""Render reads the level from the start of the line."""

from __future__ import annotations

import logging


class Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        copy = logging.makeLogRecord(record.__dict__)
        copy.levelname = copy.levelname.lower()
        return super().format(copy)
