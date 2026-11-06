"""Which browser callbacks this process will send a caller back to."""

from __future__ import annotations

import os
from urllib.parse import urlparse

_CLAUDE_REDIRECT = "https://claude.ai/api/mcp/auth_callback"
_CHATGPT_REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
_CURSOR_WEB = "https://www.cursor.com/agents/mcp/oauth/callback"
_CURSOR_APP = "cursor://anysphere.cursor-mcp/oauth/callback"


def public_base_url() -> str:
    configured = os.environ.get("ONB_PUBLIC_URL", "").strip().rstrip("/")
    if configured:
        return configured
    if os.environ.get("RENDER"):
        return "https://onb-k8ud.onrender.com"
    return "http://127.0.0.1:8000"


def allowed_emails_from_env() -> frozenset[str]:
    raw = os.environ.get("GOOGLE_ALLOWED_EMAILS", "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def redirect_allowed(uri: str) -> bool:
    """Claude, ChatGPT, and Cursor callbacks, plus a loopback port for a desktop app."""
    parsed = urlparse(uri)
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        return False
    if uri in (_CLAUDE_REDIRECT, _CURSOR_WEB, _CURSOR_APP):
        return True
    if parsed.scheme == "https" and parsed.hostname == "chatgpt.com":
        if uri == _CHATGPT_REDIRECT:
            return True
        parts = [part for part in parsed.path.split("/") if part]
        return len(parts) == 3 and parts[0] == "connector" and parts[1] == "oauth"
    if parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost"):
        return True
    return False
