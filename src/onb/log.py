"""Application logs on stdout. Render keeps those lines. Do not log answer text or file bytes."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("onb")

_FIELDS = ("application_id", "error", "field", "slot", "state", "reason_code")


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        copy = logging.makeLogRecord(record.__dict__)
        copy.levelname = copy.levelname.lower()
        return super().format(copy)


def configure() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_result(tool: str, result: dict) -> None:
    parts = [f"tool={tool}"]
    for key in _FIELDS:
        if result.get(key) is not None:
            parts.append(f"{key}={result[key]}")
    pending = result.get("pending")
    if isinstance(pending, dict) and pending.get("name"):
        parts.append(f"pending={pending['name']}")
    line = " ".join(parts)
    if result.get("error"):
        logger.warning(line)
    else:
        logger.info(line)
