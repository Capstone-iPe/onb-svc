"""Google sign-in for Claude and ChatGPT.

/mcp stays an API. A call with no bearer token gets 401. The caller's app
opens the browser, this process sends that browser to Google, and Google
sends it back here. This process then hands the caller's app Google's access
token. Later /mcp calls ask Google whether that token is still valid. The
Google client secret stays in the environment.
"""

from onb.auth.build import build_mcp
from onb.auth.google_auth_provider import GoogleAuthProvider, GoogleSignIn
from onb.auth.google_token import GoogleIdentity, inspect_access_token
from onb.auth.redirects import redirect_allowed
from onb.auth.sign_in_challenge import SignInChallenge, protected_resource_document

__all__ = [
    "GoogleAuthProvider",
    "GoogleIdentity",
    "GoogleSignIn",
    "SignInChallenge",
    "build_mcp",
    "inspect_access_token",
    "protected_resource_document",
    "redirect_allowed",
]
