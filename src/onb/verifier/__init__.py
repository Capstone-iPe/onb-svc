"""The document check. The copilot never writes accepted."""

from __future__ import annotations

import os

from onb.verifier.document_verifier import DocumentVerifier
from onb.verifier.file_bytes import file_bytes
from onb.verifier.llm_document_verifier import LlmDocumentVerifier
from onb.verifier.rules_document_verifier import RulesDocumentVerifier


def create_document_verifier() -> DocumentVerifier:
    """Return the active DocumentVerifier based on DOCUMENT_VERIFIER_MODE env var.

    Defaults to 'llm', with 'rules' providing a deterministic zero-network fallback.
    """
    mode = os.environ.get("DOCUMENT_VERIFIER_MODE", "llm").strip().lower()
    if mode == "rules":
        return RulesDocumentVerifier()
    return LlmDocumentVerifier()


__all__ = [
    "DocumentVerifier",
    "LlmDocumentVerifier",
    "RulesDocumentVerifier",
    "create_document_verifier",
    "file_bytes",
]
