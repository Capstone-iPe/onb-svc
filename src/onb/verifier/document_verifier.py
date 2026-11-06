"""The document check. A real checker and the mock both implement this.

save_file asks the checker, then stores the result on the slot. The checker does not write the application row.
"""

from __future__ import annotations

from typing import Protocol


class DocumentVerifier(Protocol):
    """Decide whether an uploaded file is accepted for one slot."""

    def verify(self, slot: str, shop_name: str, file: bytes, submit_date: str) -> dict:
        """Return the decision for this file.

        slot is the upload name: business_registration, owner_id, bank_proof, shopfront_photo, or dpa_addendum.
        shop_name is the legal name already saved on the application.
        file is the upload bytes.
        submit_date is an ISO date. The shopfront age check uses it.

        The dict has accepted and reason_code. accepted is true when the file may be stored as accepted, and reason_code is ok. When accepted is false, reason_code names why and the slot stays pending.
        """
        ...
