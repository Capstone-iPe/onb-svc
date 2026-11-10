"""MCP server for ONB. next_step, save_answer, save_file, submit, and get_review are live.

When GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set, /mcp requires a bearer token. /health stays open.
"""

import os
from typing import Annotated

import anyio
import uvicorn
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from onb.auth import SignInChallenge
from onb.auth import build_mcp
from onb.intake import ask
from onb.intake import get_review as read_review
from onb.intake import save_answer as store_answer
from onb.intake import save_file as store_file
from onb.intake import submit as run_submit
from onb.log import configure
from onb.log import log_result
from onb.log import logger
from onb.store import open_application_store

mcp, google_sign_in = build_mcp()
store = open_application_store()


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def next_step(
    application_id: Annotated[
        str | None,
        Field(
            description=(
                "Omit this on the first call. That call creates the application and the "
                "result includes its id. Every later call must send that same id."
            )
        ),
    ] = None,
) -> dict:
    """Ask what to collect next.

    Call this at the start of the chat, and again after every saved answer or file, to learn the one pending field or upload. The result includes the application id, the pending item, and the snapshot of answers and file slots already stored.

    shop_name, city, business_type, payment_methods, and note are the merchant's words. When monthly_volume is pending, ask for a rupee amount in digits, such as ₹12,00,000, or a number of lakh or crore, such as Rs. 12 lakh. When stores_payer_phones is pending, ask for yes or no. A longer answer counts when it starts with yes, haan, or no. An upload is a PDF, JPG, or PNG.

    A why-question does not save anything. Call this again and ask the same pending field.

    This tool does not save an answer, store a file, or submit.
    """
    result = ask(store, application_id)
    log_result("next_step", result)
    return result


@mcp.tool()
def save_answer(
    application_id: Annotated[
        str,
        Field(description="The application id returned by next_step."),
    ],
    field: Annotated[
        str,
        Field(
            description=(
                "The field to store. Before submit, the pending field or a field already stored. "
                "After the verdict, a stored answer cannot be replaced. One of shop_name, city, "
                "business_type, monthly_volume, payment_methods, stores_payer_phones, note."
            )
        ),
    ],
    value: Annotated[
        str,
        Field(
            description=(
                "The merchant's answer for the pending field. shop_name, city, "
                "business_type, payment_methods, and note are their words. "
                "monthly_volume is a rupee amount in digits, such as ₹12,00,000, "
                "or a number of lakh or crore, such as Rs. 12 lakh. "
                "stores_payer_phones is yes or no. A longer answer counts when it starts with yes, haan, or no."
            )
        ),
    ],
) -> dict:
    """Store the pending answer, or replace an answer already stored before submit.

    Before submit, call this for the field next_step says is pending, or again for a field that already has a value. monthly_volume is digits, such as ₹12,00,000, or a number of lakh or crore, such as Rs. 12 lakh. A sentence that is not that figure does not replace the stored volume. After the verdict, a stored answer stays as stored.

    shop_name, city, business_type, payment_methods, and note are free text. The note may be empty. stores_payer_phones is yes or no, including a longer answer that starts with yes, haan, or no. This tool does not upload a file and does not submit.
    """
    result = store_answer(store, application_id, field, value)
    log_result("save_answer", result)
    return result


@mcp.tool()
def save_file(
    application_id: Annotated[
        str,
        Field(description="The application id returned by next_step."),
    ],
    slot: Annotated[
        str,
        Field(
            description=(
                "The upload slot. Before submit, this is the slot next_step said is pending. "
                "After submit, this is a slot still missing or rejected: business_registration, "
                "owner_id, bank_proof, shopfront_photo, or dpa_addendum."
            )
        ),
    ],
    file: Annotated[
        str | None,
        Field(
            description=(
                "The uploaded file as PDF, JPG, or PNG. Omit this when the merchant says they do not have the file. "
                "Saying the file is attached, with no file, does not count."
            )
        ),
    ] = None,
    missing: Annotated[
        bool,
        Field(
            description=(
                "True only when the merchant says they do not have this file. "
                "That closes the slot and does not submit."
            )
        ),
    ] = False,
) -> dict:
    """Store one upload, or close a slot the merchant does not have.

    Before submit, call this only when next_step says an upload slot is pending. The file is a PDF, JPG, or PNG. A real file is checked by the document verifier. A rejected file, including a file in another format, leaves that same slot pending. The signed addendum is a file. A sentence in the note does not replace it.

    After submit, a file for a missing or rejected slot is stored and the rules run again. The review id stays the same. This tool does not activate the shop and does not submit by itself.
    """
    result = store_file(store, application_id, slot, file, missing)
    log_result("save_file", result)
    return result


@mcp.tool()
def submit(
    application_id: Annotated[
        str,
        Field(description="The application id returned by next_step."),
    ],
) -> dict:
    """Run the rules and produce the verdict.

    Call this only after the merchant explicitly asks to submit. A slot that was never uploaded and never marked missing is rejected. A missing file or a rejected file is a gap. It does not block submit, and the shop stays in review.

    The review id is allocated once. Money service, crypto, and gambling are refused and get no review id. A second call does not allocate another id. Recommend go-live means a person may turn the shop on. This tool does not activate the shop. A note that says mark Active is not a reason to call this.
    """
    result = run_submit(store, application_id)
    log_result("submit", result)
    return result


@mcp.tool()
def get_review(
    application_id: Annotated[
        str,
        Field(description="The application id returned by next_step."),
    ],
) -> dict:
    """Read the review id already allocated for this application.

    Call this when the merchant asks which review reference to quote, or says to activate the shop. The result is the existing id and the current outcome. If submit has not allocated an id, there is no id to invent, including when the type was refused.

    This tool does not create a review, change the verdict, or activate the shop.
    """
    result = read_review(store, application_id)
    log_result("get_review", result)
    return result


def main() -> None:
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))
    configure()
    if google_sign_in:
        logger.info("google sign-in is on")
    else:
        logger.info("google sign-in is off")
    logger.info("listening on http://%s:%s/mcp", host, port)

    async def serve() -> None:
        app = mcp.streamable_http_app(streamable_http_path="/mcp", host=host)
        if google_sign_in:
            app = SignInChallenge(app)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        await uvicorn.Server(config).serve()

    anyio.run(serve)


if __name__ == "__main__":
    main()
