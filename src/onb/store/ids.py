"""Application ids. The row key, not the review id."""

from __future__ import annotations

import uuid


def new_application_id() -> str:
    return "app_" + uuid.uuid4().hex[:12]
