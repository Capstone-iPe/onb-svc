"""This process is the authorization server. Google is the sign-in page.

After Google signs the person in, the MCP bearer is Google's access token.
Every later /mcp call asks Google whether that token is still valid.
"""

from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from onb.auth.google_token import GoogleIdentity, inspect_access_token
from onb.auth.redirects import redirect_allowed
from onb.clients import ClientDirectory, MemoryClients
from onb.log import logger

ACCESS_SECONDS = 60 * 60
REFRESH_SECONDS = 30 * 24 * ACCESS_SECONDS
CODE_SECONDS = 5 * 60
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"


@dataclass
class _Pending:
    client_id: str
    params: AuthorizationParams


@dataclass(frozen=True)
class GoogleSignIn:
    email: str
    access_token: str
    refresh_token: str | None = None
    expires_in: int = ACCESS_SECONDS


@dataclass
class _Session:
    access: str
    refresh: str


class GoogleAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(
        self,
        *,
        google_client_id: str,
        google_client_secret: str,
        public_url: str,
        resource_url: str,
        allowed_emails: frozenset[str] = frozenset(),
        allowed_audiences: frozenset[str] | None = None,
        exchange_code=None,
        inspect_token=None,
        refresh_google=None,
        clients: ClientDirectory | None = None,
    ) -> None:
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret
        self.public_url = public_url.rstrip("/")
        self.resource_url = resource_url
        self.allowed_emails = allowed_emails
        self.allowed_audiences = allowed_audiences or frozenset({google_client_id})
        self._exchange_code = exchange_code or self.exchange_google_code
        self._inspect_token = inspect_token or self._inspect
        self._refresh_google = refresh_google or self.refresh_google_token
        self.google_redirect_uri = f"{self.public_url}/auth/google/callback"
        self.clients = clients if clients is not None else MemoryClients()
        self.pending: dict[str, _Pending] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.google_by_code: dict[str, GoogleSignIn] = {}
        self.access_tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.google_refresh: dict[str, str] = {}
        self.sessions: dict[str, _Session] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [uri for uri in (client_info.redirect_uris or []) if redirect_allowed(str(uri))]
        if not uris:
            raise RegistrationError("invalid_redirect_uri", "Redirect URI is not allowed")
        client_info.redirect_uris = uris
        self.clients.put(client_info)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not redirect_allowed(str(params.redirect_uri)):
            raise AuthorizeError("invalid_request", "Redirect URI is not allowed")
        if params.resource and not _same_resource(params.resource, self.resource_url):
            raise AuthorizeError("invalid_target", "Unknown resource")
        state = secrets.token_urlsafe(32)
        self.pending[state] = _Pending(client.client_id, params)
        query = urlencode(
            {
                "client_id": self.google_client_id,
                "redirect_uri": self.google_redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return f"{GOOGLE_AUTHORIZE}?{query}"

    async def handle_google_callback(self, request: Request) -> Response:
        state = request.query_params.get("state")
        pending = self.pending.pop(state, None) if state else None
        if pending is None or request.query_params.get("error"):
            logger.warning("google sign-in failed")
            return PlainTextResponse("Sign-in failed", status_code=400)
        code = request.query_params.get("code")
        if not code:
            logger.warning("google sign-in failed")
            return PlainTextResponse("Sign-in failed", status_code=400)
        try:
            signed_in = self._exchange_code(code)
        except Exception:
            logger.warning("google sign-in failed")
            return PlainTextResponse("Sign-in failed", status_code=400)
        signed_in = _as_sign_in(signed_in)
        if signed_in is None or not self._email_allowed(signed_in.email):
            logger.warning("google sign-in rejected")
            return PlainTextResponse("This Google account is not allowed", status_code=403)
        issued = secrets.token_urlsafe(32)
        self.codes[issued] = AuthorizationCode(
            code=issued,
            scopes=_scopes(pending.params.scopes),
            expires_at=time.time() + CODE_SECONDS,
            client_id=pending.client_id,
            code_challenge=pending.params.code_challenge,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            resource=self.resource_url,
            subject=signed_in.email,
        )
        self.google_by_code[issued] = signed_in
        logger.info("google sign-in accepted")
        return RedirectResponse(
            construct_redirect_uri(
                str(pending.params.redirect_uri),
                code=issued,
                state=pending.params.state,
                iss=self.public_url,
            ),
            status_code=302,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self.codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self.codes.pop(authorization_code.code, None)
        signed_in = self.google_by_code.pop(authorization_code.code, None)
        if signed_in is None:
            raise ValueError("google sign-in is missing")
        return self._issue(
            authorization_code.client_id,
            authorization_code.scopes,
            signed_in,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return self.refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        google_refresh = self.google_refresh.get(refresh_token.token)
        if not google_refresh:
            raise ValueError("google refresh token is missing")
        signed_in = self._refresh_google(google_refresh)
        self._drop_token(refresh_token.token)
        return self._issue(refresh_token.client_id, scopes, signed_in)

    async def load_access_token(self, token: str) -> AccessToken | None:
        identity = self._inspect_token(token)
        if identity is None:
            return None
        if not self._email_allowed(identity.email):
            return None
        now = int(time.time())
        expires_at = now + identity.expires_in if identity.expires_in else now + ACCESS_SECONDS
        return AccessToken(
            token=token,
            client_id=identity.audience,
            scopes=["openid", "email"],
            expires_at=expires_at,
            resource=self.resource_url,
            subject=identity.email,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self._drop_token(token.token)

    def exchange_google_code(self, code: str) -> GoogleSignIn:
        token = _post_form(
            GOOGLE_TOKEN,
            {
                "code": code,
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret,
                "redirect_uri": self.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        access = token.get("access_token")
        if not isinstance(access, str) or not access:
            raise ValueError("google token response has no access_token")
        id_token = token.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise ValueError("google token response has no id_token")
        info = _post_form(GOOGLE_TOKENINFO, {"id_token": id_token})
        if info.get("aud") != self.google_client_id:
            raise ValueError("google token audience mismatch")
        if info.get("email_verified") not in (True, "true"):
            raise ValueError("google email is not verified")
        email = info.get("email")
        if not isinstance(email, str) or "@" not in email:
            raise ValueError("google token has no email")
        refresh = token.get("refresh_token")
        expires = token.get("expires_in", ACCESS_SECONDS)
        try:
            expires_in = int(expires)
        except (TypeError, ValueError):
            expires_in = ACCESS_SECONDS
        return GoogleSignIn(
            email=email.strip().lower(),
            access_token=access,
            refresh_token=refresh if isinstance(refresh, str) and refresh else None,
            expires_in=expires_in,
        )

    def refresh_google_token(self, refresh_token: str) -> GoogleSignIn:
        token = _post_form(
            GOOGLE_TOKEN,
            {
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        access = token.get("access_token")
        if not isinstance(access, str) or not access:
            raise ValueError("google refresh has no access_token")
        identity = inspect_access_token(access, self.allowed_audiences)
        if identity is None:
            raise ValueError("google refresh was rejected")
        expires = token.get("expires_in", identity.expires_in or ACCESS_SECONDS)
        try:
            expires_in = int(expires)
        except (TypeError, ValueError):
            expires_in = ACCESS_SECONDS
        new_refresh = token.get("refresh_token")
        return GoogleSignIn(
            email=identity.email,
            access_token=access,
            refresh_token=(
                new_refresh if isinstance(new_refresh, str) and new_refresh else refresh_token
            ),
            expires_in=expires_in,
        )

    def _inspect(self, token: str) -> GoogleIdentity | None:
        return inspect_access_token(token, self.allowed_audiences)

    def _email_allowed(self, email: str) -> bool:
        if not self.allowed_emails:
            return True
        return email.strip().lower() in self.allowed_emails

    def _issue(self, client_id: str, scopes: list[str], signed_in: GoogleSignIn) -> OAuthToken:
        access = signed_in.access_token
        refresh = secrets.token_urlsafe(32)
        session = secrets.token_urlsafe(16)
        now = int(time.time())
        self.access_tokens[access] = AccessToken(
            token=access,
            client_id=client_id,
            scopes=list(scopes),
            expires_at=now + int(signed_in.expires_in or ACCESS_SECONDS),
            resource=self.resource_url,
            subject=signed_in.email,
        )
        self.refresh_tokens[refresh] = RefreshToken(
            token=refresh,
            client_id=client_id,
            scopes=list(scopes),
            expires_at=now + REFRESH_SECONDS,
            resource=self.resource_url,
            subject=signed_in.email,
        )
        if signed_in.refresh_token:
            self.google_refresh[refresh] = signed_in.refresh_token
        self.sessions[session] = _Session(access, refresh)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=int(signed_in.expires_in or ACCESS_SECONDS),
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    def _drop_token(self, token: str) -> None:
        for session, pair in list(self.sessions.items()):
            if token in (pair.access, pair.refresh):
                self.access_tokens.pop(pair.access, None)
                self.refresh_tokens.pop(pair.refresh, None)
                self.google_refresh.pop(pair.refresh, None)
                self.sessions.pop(session, None)


def _as_sign_in(value: object) -> GoogleSignIn | None:
    if isinstance(value, GoogleSignIn):
        return value
    if isinstance(value, str) and "@" in value:
        return GoogleSignIn(email=value.strip().lower(), access_token=secrets.token_urlsafe(32))
    return None


def _scopes(requested: list[str] | None) -> list[str]:
    scopes = list(requested or ["openid", "email"])
    if "openid" not in scopes:
        scopes.insert(0, "openid")
    return scopes


def _same_resource(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _post_form(url: str, form: dict[str, str]) -> dict:
    request = urllib.request.Request(url, data=urlencode(form).encode(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise ValueError("google rejected the sign-in") from exc
    if not isinstance(payload, dict):
        raise ValueError("google rejected the sign-in")
    return payload
