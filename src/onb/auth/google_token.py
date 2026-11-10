"""Ask Google whether a bearer string is still a valid access token."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    subject: str
    audience: str
    expires_in: int | None = None


def audiences_from_env(primary: str, raw: str = "") -> frozenset[str]:
    allowed = {primary.strip()} if primary.strip() else set()
    for part in raw.split(","):
        value = part.strip()
        if value:
            allowed.add(value)
    return frozenset(allowed)


def inspect_access_token(token: str, allowed_audiences: frozenset[str]) -> GoogleIdentity | None:
    """Return the signed-in person when Google still accepts this access token.

    A blank token, a rejected token, an unverified email, or an audience outside
    the allow-list writes nothing and returns None.
    """
    text = (token or "").strip()
    if not text or not allowed_audiences:
        return None
    try:
        info = _get_json(f"{GOOGLE_TOKENINFO}?{urlencode({'access_token': text})}")
    except ValueError:
        return None
    audience = str(info.get("aud") or info.get("azp") or "").strip()
    if audience not in allowed_audiences:
        return None
    try:
        profile = _get_json(
            GOOGLE_USERINFO,
            headers={"Authorization": f"Bearer {text}"},
        )
    except ValueError:
        return None
    if profile.get("email_verified") not in (True, "true"):
        return None
    email = profile.get("email")
    subject = profile.get("sub")
    if not isinstance(email, str) or "@" not in email:
        return None
    if not isinstance(subject, str) or not subject.strip():
        return None
    expires = info.get("expires_in")
    try:
        expires_in = int(expires) if expires is not None else None
    except (TypeError, ValueError):
        expires_in = None
    return GoogleIdentity(
        email=email.strip().lower(),
        subject=subject.strip(),
        audience=audience,
        expires_in=expires_in,
    )


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise ValueError("google rejected the token") from exc
    if not isinstance(payload, dict):
        raise ValueError("google rejected the token")
    return payload
