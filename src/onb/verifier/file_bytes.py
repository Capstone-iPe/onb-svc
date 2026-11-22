"""Turn the copilot's file string into bytes. "Attached" with no file is empty."""

from __future__ import annotations

import base64


def file_bytes(file: str | bytes | None) -> bytes:
    if file is None:
        return b""
    if isinstance(file, bytes):
        return file
    text = file.strip()
    if text == "" or text.lower() == "attached":
        return b""
    payload = text
    if payload.startswith("data:") and "base64," in payload:
        payload = payload.split("base64,", 1)[1]
    try:
        decoded = base64.b64decode(payload, validate=True)
    except Exception:
        decoded = b""
    if decoded:
        return decoded
    return text.encode("utf-8")
