"""Google sign-in for Claude and ChatGPT.

/mcp stays an API. A call with no bearer token gets 401. The caller's app
opens the browser, this process sends that browser to Google, and Google
sends it back here. This process then hands the caller's app its own access
token. The Google client secret stays in the environment.
"""

from onb.auth.build import build_mcp
from onb.auth.google_auth_provider import GoogleAuthProvider
from onb.auth.redirects import redirect_allowed
from onb.auth.sign_in_challenge import SignInChallenge, protected_resource_document

__all__ = [
    "GoogleAuthProvider",
    "SignInChallenge",
    "build_mcp",
    "protected_resource_document",
    "redirect_allowed",
]
