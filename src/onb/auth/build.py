"""Build the MCP process with Google sign-in when the client id and secret are set."""

from __future__ import annotations

import os

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from onb.auth.google_auth_provider import GoogleAuthProvider
from onb.auth.redirects import allowed_audiences_from_env, allowed_emails_from_env, public_base_url
from onb.auth.sign_in_challenge import protected_resource_document
from onb.clients import client_directory


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
        allowed_audiences=allowed_audiences_from_env(client_id),
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
