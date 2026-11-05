import asyncio
import base64
import hashlib
import json
from urllib.parse import parse_qs, urlencode, urlparse

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from starlette.responses import JSONResponse

from onb.auth import GoogleAuthProvider, redirect_allowed


def test_redirect_allow_list():
    assert redirect_allowed("https://claude.ai/api/mcp/auth_callback")
    assert redirect_allowed("https://chatgpt.com/connector_platform_oauth_redirect")
    assert redirect_allowed("https://chatgpt.com/connector/oauth/cb_123")
    assert redirect_allowed("http://127.0.0.1:54321/callback")
    assert redirect_allowed("http://localhost:9/callback")
    assert not redirect_allowed("https://evil.example/callback")
    assert not redirect_allowed("https://claude.ai/api/mcp/auth_callback?next=https://evil.example")
    assert not redirect_allowed("https://chatgpt.com/connector/oauth/cb_123/extra")
    assert not redirect_allowed("https://127.0.0.1/callback")


def test_mcp_without_a_bearer_is_401_and_health_stays_open():
    app, _provider = _app(lambda _code: "owner@gmail.com")

    async def run():
        missing = await _call(app, "POST", "/mcp")
        health = await _call(app, "GET", "/health")
        resource = await _call(app, "GET", "/.well-known/oauth-protected-resource/mcp")
        server = await _call(app, "GET", "/.well-known/oauth-authorization-server")
        return missing, health, resource, server

    missing, health, resource, server = asyncio.run(run())
    assert missing[0] == 401
    assert (
        'resource_metadata="http://127.0.0.1:8000/.well-known/oauth-protected-resource/mcp"'
        in missing[1]["www-authenticate"]
    )
    assert health[0] == 200
    assert json.loads(health[2]) == {"status": "ok"}
    resource_body = json.loads(resource[2])
    assert resource_body["resource"] == "http://127.0.0.1:8000/mcp"
    assert resource_body["authorization_servers"] == ["http://127.0.0.1:8000"]
    server_body = json.loads(server[2])
    assert server_body["issuer"] == "http://127.0.0.1:8000"
    assert server_body["code_challenge_methods_supported"] == ["S256"]
    assert server_body["registration_endpoint"] == "http://127.0.0.1:8000/register"


def test_google_callback_issues_a_token_and_a_bad_verifier_does_not():
    app, provider = _app(lambda _code: "owner@gmail.com")
    verifier = "a" * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

    async def run():
        registered = await _call(
            app,
            "POST",
            "/register",
            json_body={
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": "openid email",
            },
        )
        client_id = json.loads(registered[2])["client_id"]
        started = await _call(
            app,
            "GET",
            "/authorize",
            query={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "abc",
                "scope": "openid email",
                "resource": "http://127.0.0.1:8000/mcp",
            },
        )
        google = urlparse(started[1]["location"])
        query = parse_qs(google.query)
        callback = await _call(
            app,
            "GET",
            "/auth/google/callback",
            query={"code": "google-code", "state": query["state"][0]},
        )
        returned = parse_qs(urlparse(callback[1]["location"]).query)
        form = {
            "grant_type": "authorization_code",
            "code": returned["code"][0],
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "resource": "http://127.0.0.1:8000/mcp",
        }
        rejected = await _call(app, "POST", "/token", form={**form, "code_verifier": "b" * 43})
        accepted = await _call(app, "POST", "/token", form={**form, "code_verifier": verifier})
        return registered, started, google, query, callback, returned, rejected, accepted

    registered, started, google, query, callback, returned, rejected, accepted = asyncio.run(run())
    assert registered[0] == 201
    assert started[0] == 302
    assert google.netloc == "accounts.google.com"
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/auth/google/callback"]
    assert callback[0] == 302
    assert urlparse(callback[1]["location"]).netloc == "claude.ai"
    assert returned["state"] == ["abc"]
    assert returned["iss"] == ["http://127.0.0.1:8000"]
    assert rejected[0] == 400
    assert accepted[0] == 200
    token = json.loads(accepted[2])["access_token"]
    loaded = asyncio.run(provider.load_access_token(token))
    assert loaded is not None
    assert loaded.subject == "owner@gmail.com"
    assert loaded.resource == "http://127.0.0.1:8000/mcp"
    assert b"owner@gmail.com" not in accepted[2]


def test_a_foreign_redirect_and_a_foreign_account_are_refused():
    app, _provider = _app(lambda _code: "other@gmail.com", allowed=frozenset({"owner@gmail.com"}))

    async def run():
        foreign = await _call(
            app,
            "POST",
            "/register",
            json_body={
                "redirect_uris": ["https://evil.example/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        registered = await _call(
            app,
            "POST",
            "/register",
            json_body={
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": "openid email",
            },
        )
        started = await _call(
            app,
            "GET",
            "/authorize",
            query={
                "client_id": json.loads(registered[2])["client_id"],
                "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
                "response_type": "code",
                "code_challenge": "challenge",
                "code_challenge_method": "S256",
                "state": "abc",
                "resource": "http://127.0.0.1:8000/mcp",
            },
        )
        state = parse_qs(urlparse(started[1]["location"]).query)["state"][0]
        rejected = await _call(app, "GET", "/auth/google/callback", query={"code": "google-code", "state": state})
        return foreign, rejected

    foreign, rejected = asyncio.run(run())
    assert foreign[0] == 400
    assert json.loads(foreign[2])["error"] == "invalid_redirect_uri"
    assert rejected[0] == 403
    assert b"other@gmail.com" not in rejected[2]


def _app(exchange, allowed=frozenset()):
    provider = GoogleAuthProvider(
        google_client_id="google-client",
        google_client_secret="google-secret",
        public_url="http://127.0.0.1:8000",
        resource_url="http://127.0.0.1:8000/mcp",
        allowed_emails=allowed,
        exchange_code=exchange,
    )
    server = MCPServer(
        "onb",
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url="http://127.0.0.1:8000",
            resource_server_url="http://127.0.0.1:8000/mcp",
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

    @server.custom_route("/health", methods=["GET"])
    async def health(_request):
        return JSONResponse({"status": "ok"})

    @server.custom_route("/auth/google/callback", methods=["GET"])
    async def google_callback(request):
        return await provider.handle_google_callback(request)

    return server.streamable_http_app(), provider


async def _call(app, method, path, query=None, json_body=None, form=None):
    payload = b""
    headers = []
    if json_body is not None:
        payload = json.dumps(json_body).encode()
        headers.append((b"content-type", b"application/json"))
    elif form is not None:
        payload = urlencode(form).encode()
        headers.append((b"content-type", b"application/x-www-form-urlencoded"))
    headers.append((b"content-length", str(len(payload)).encode()))
    query_string = urlencode(query or {}).encode()
    status = {}
    chunks = []

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
            status["headers"] = {key.decode().lower(): value.decode() for key, value in message["headers"]}
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query_string,
            "headers": headers,
            "client": ("127.0.0.1", 123),
            "server": ("127.0.0.1", 8000),
        },
        receive,
        send,
    )
    return status["code"], status["headers"], b"".join(chunks)
