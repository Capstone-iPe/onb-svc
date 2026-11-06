"""The document check. The copilot never writes accepted."""

from onb.verifier.document_verifier import DocumentVerifier
from onb.verifier.file_bytes import file_bytes
from onb.verifier.mock_document_verifier import MockDocumentVerifier

__all__ = ["DocumentVerifier", "MockDocumentVerifier", "file_bytes"]
