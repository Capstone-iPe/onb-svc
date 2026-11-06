"""Application logs on stderr. Render keeps those lines. Do not log answer text or file bytes."""

from __future__ import annotations

import logging
import sys

from onb.log.formatter import Formatter

logger = logging.getLogger("onb")

_FIELDS = ("application_id", "error", "field", "slot", "state", "reason_code")


def configure() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_result(tool: str, result: dict) -> None:
    parts = [f"tool={tool}"]
    for key in _FIELDS:
        if result.get(key) is not None:
            parts.append(f"{key}={result[key]}")
    pending = result.get("pending")
    if isinstance(pending, dict) and pending.get("name"):
        parts.append(f"pending={pending['name']}")
    verdict = result.get("verdict")
    if isinstance(verdict, dict) and verdict.get("outcome"):
        parts.append(f"outcome={verdict['outcome']}")
    line = " ".join(parts)
    if result.get("error"):
        logger.warning(line)
    else:
        logger.info(line)
