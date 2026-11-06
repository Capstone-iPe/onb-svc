"""Google sign-in for Claude and ChatGPT.

/mcp stays an API. A call with no bearer token gets 401. The caller's app
opens the browser, this process sends that browser to Google, and Google
sends it back here. This process then hands the caller's app its own access
token. The Google client secret stays in the environment.
"""

import json
import os
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from onb.log import logger

ACCESS_SECONDS = 60 * 60
REFRESH_SECONDS = 30 * 24 * ACCESS_SECONDS
CODE_SECONDS = 5 * 60
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"

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


class MemoryClients:
    """The process remembers registrations until it stops."""

    def __init__(self) -> None:
        self._rows: dict[str, OAuthClientInformationFull] = {}

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._rows.get(client_id)

    def put(self, client: OAuthClientInformationFull) -> None:
        self._rows[client.client_id] = client


class PostgresClients:
    """ChatGPT keeps the client id. A restart must still know it."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._ready = False

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        self._ensure()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT record FROM oauth_clients WHERE client_id = %s",
                (client_id,),
            ).fetchone()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(row[0])

    def put(self, client: OAuthClientInformationFull) -> None:
        from psycopg.types.json import Jsonb

        self._ensure()
        record = client.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO oauth_clients (client_id, record)
                VALUES (%s, %s)
                ON CONFLICT (client_id) DO UPDATE SET record = EXCLUDED.record
                """,
                (client.client_id, Jsonb(record)),
            )

    def _connect(self):
        import psycopg

        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        return psycopg.connect(url, autocommit=True)

    def _ensure(self) -> None:
        if self._ready:
            return
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id text PRIMARY KEY,
                    record jsonb NOT NULL
                )
                """
            )
        self._ready = True


def client_directory() -> MemoryClients | PostgresClients:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return PostgresClients(url)
    return MemoryClients()


@dataclass
class _Pending:
    client_id: str
    params: AuthorizationParams


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
        exchange_code=None,
        clients=None,
    ) -> None:
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret
        self.public_url = public_url.rstrip("/")
        self.resource_url = resource_url
        self.allowed_emails = allowed_emails
        self._exchange_code = exchange_code or self.exchange_google_code
        self.google_redirect_uri = f"{self.public_url}/auth/google/callback"
        self.clients = clients if clients is not None else MemoryClients()
        self.pending: dict[str, _Pending] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.access_tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
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
                "access_type": "online",
                "prompt": "select_account",
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
            email = self._exchange_code(code)
        except Exception:
            logger.warning("google sign-in failed")
            return PlainTextResponse("Sign-in failed", status_code=400)
        if not isinstance(email, str) or not self._email_allowed(email):
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
            subject=email.strip().lower(),
        )
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
        return self._issue(authorization_code.client_id, authorization_code.scopes, authorization_code.subject)

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
        self._drop_token(refresh_token.token)
        return self._issue(refresh_token.client_id, scopes, refresh_token.subject)

    async def load_access_token(self, token: str) -> AccessToken | None:
        found = self.access_tokens.get(token)
        if found is None:
            return None
        if found.expires_at is not None and found.expires_at < int(time.time()):
            return None
        return found

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self._drop_token(token.token)

    def exchange_google_code(self, code: str) -> str:
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
        return email.strip().lower()

    def _email_allowed(self, email: str) -> bool:
        if not self.allowed_emails:
            return True
        return email.strip().lower() in self.allowed_emails

    def _issue(self, client_id: str, scopes: list[str], subject: str | None) -> OAuthToken:
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        session = secrets.token_urlsafe(16)
        now = int(time.time())
        self.access_tokens[access] = AccessToken(
            token=access,
            client_id=client_id,
            scopes=list(scopes),
            expires_at=now + ACCESS_SECONDS,
            resource=self.resource_url,
            subject=subject,
        )
        self.refresh_tokens[refresh] = RefreshToken(
            token=refresh,
            client_id=client_id,
            scopes=list(scopes),
            expires_at=now + REFRESH_SECONDS,
            resource=self.resource_url,
            subject=subject,
        )
        self.sessions[session] = _Session(access, refresh)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_SECONDS,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    def _drop_token(self, token: str) -> None:
        for session, pair in list(self.sessions.items()):
            if token in (pair.access, pair.refresh):
                self.access_tokens.pop(pair.access, None)
                self.refresh_tokens.pop(pair.refresh, None)
                self.sessions.pop(session, None)


def build_mcp() -> tuple[MCPServer, bool]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return MCPServer("onb"), False
    public = public_base_url()
    resource = f"{public}/mcp"
    provider = GoogleAuthProvider(
        google_client_id=client_id,
        google_client_secret=client_secret,
        public_url=public,
        resource_url=resource,
        allowed_emails=allowed_emails_from_env(),
        clients=client_directory(),
    )
    server = MCPServer(
        "onb",
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=public,
            resource_server_url=resource,
            required_scopes=["openid"],
            validate_token_resource=True,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["openid", "email", "profile", "offline_access"],
                default_scopes=["openid", "email"],
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )

    @server.custom_route("/auth/google/callback", methods=["GET"])
    async def google_callback(request: Request) -> Response:
        return await provider.handle_google_callback(request)

    @server.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
    async def protected_resource_root(_request: Request) -> JSONResponse:
        return JSONResponse(
            protected_resource_document(public, resource),
            headers={"Cache-Control": "public, max-age=3600"},
        )

    return server, True


class SignInChallenge:
    """A call with no token is a sign-in challenge, not a rejected token.

    The MCP library always writes error="invalid_token". A client treats that as a failed call and does not open the browser.
    """

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
