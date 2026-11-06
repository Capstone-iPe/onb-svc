"""A call with no token is a sign-in challenge, not a rejected token.

The MCP library always writes error="invalid_token". A client treats that as a failed call and does not open the browser.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send


class SignInChallenge:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        had_token = _authorization_present(scope)

        async def send_challenge(message: dict) -> None:
            if message["type"] == "http.response.start" and message.get("status") == 401:
                message = {**message, "headers": _challenge_headers(message.get("headers", []), had_token)}
            await send(message)

        await self.app(scope, receive, send_challenge)


def protected_resource_document(public: str, resource: str) -> dict[str, object]:
    return {
        "resource": resource,
        "authorization_servers": [public],
        "scopes_supported": ["openid"],
        "bearer_methods_supported": ["header"],
    }


def _authorization_present(scope: Scope) -> bool:
    for key, value in scope.get("headers") or []:
        if key.lower() == b"authorization" and value.strip():
            return True
    return False


def _challenge_headers(headers: list[tuple[bytes, bytes]], had_token: bool) -> list[tuple[bytes, bytes]]:
    metadata = None
    kept = []
    for key, value in headers:
        if key.lower() == b"www-authenticate":
            metadata = _resource_metadata(value.decode())
            continue
        kept.append((key, value))
    if metadata is None:
        return headers
    if had_token:
        challenge = f'Bearer error="invalid_token", resource_metadata="{metadata}", scope="openid"'
    else:
        challenge = f'Bearer resource_metadata="{metadata}", scope="openid"'
    kept.append((b"www-authenticate", challenge.encode()))
    names = {key.lower() for key, _value in kept}
    if b"access-control-expose-headers" not in names:
        kept.append((b"access-control-expose-headers", b"WWW-Authenticate"))
    if b"access-control-allow-origin" not in names:
        kept.append((b"access-control-allow-origin", b"*"))
    return kept


def _resource_metadata(header: str) -> str | None:
    marker = 'resource_metadata="'
    start = header.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = header.find('"', start)
    if end < 0:
        return None
    return header[start:end]
