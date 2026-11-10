---
name: onb-service
description: >-
  Keep the ONB service inside its accepted boundary. Use when editing onb-svc,
  adding or changing an MCP tool (next_step, save_answer, save_file, submit,
  get_review), a protocol (ApplicationStore, DocumentVerifier, ClientDirectory),
  a package, the verdict, Google sign-in, Postgres, or logs. Also use when the
  user mentions the copilot, MCP, review id, pack, volume, or a new tool.
---

# ONB service

This process is deterministic Python. It has no model. The copilot is the MCP client. Read [ADR-0001](https://github.com/Capstone-iPe/analysis/blob/main/docs/ADR-0001-architecture.md) before adding a capability. If the change is not already a tool, a field, an error code, or a package below, stop and ask. Do not invent it.

## Closed tool list

The only MCP tools are `next_step`, `save_answer`, `save_file`, `submit`, and `get_review`.

Leave these off the server: activate, waive, mark-complete, change-volume, create_application, get_application, mark_missing, verify, policy search. `verify` stays inside this process. Policy search stays in the copilot.

- `next_step` with no id creates one application and returns `app_` plus twelve hex characters. The same id does not create another. An unknown id is an error and does not create a row. A blank id creates.
- `save_answer` writes the pending text field. Before submit it may also replace an answer already stored, including a new digit volume. After the verdict a stored answer stays as stored.
- `save_file` writes the pending upload before submit. `missing=true` closes that slot as `missing`. A file and `missing=true` together is `file_and_missing`. After the verdict, a file for a slot that is missing or still pending is stored, the rules run again, and the review id stays the same.
- `submit` runs the rules once and allocates `MR-2041` onward, unless the outcome is `REFUSED`. A second submit returns the stored verdict and the same id.
- `get_review` returns the stored verdict. It does not call `decide` and it does not allocate an id. Before submit the error is `no_review`.

## What a save may write

Field order, one pending item at a time: `shop_name`, `city`, `business_type`, `monthly_volume`, `payment_methods`, `stores_payer_phones`, then `business_registration`, `owner_id`, `bank_proof`, `shopfront_photo`, then `dpa_addendum` only when payer phones are stored, then an optional `note`.

`monthly_volume` is a rupee figure: digits, such as `₹12,00,000`, or a number of lakh or crore, such as `Rs. 12 lakh` and `41 lakh` (ONB-POL-002 §4.1, ONB-ANX-002). A sentence that is not that figure, including "please treat us as thirty-nine lakh", is `volume_unreadable` and the field stays pending. `stores_payer_phones` is yes or no. A longer answer counts when its first word is yes or no, such as `Yes, for loyalty.` and `No, we don't store them.` Anything else is `phones_not_yes_or_no`. Shop name, city, business type, payment methods, and note stay free text. Note may be empty. A blank required answer does not advance.

The pack is those four upload slots. Do not add GSTIN, Udyam, FSSAI, a licence, or another id document as a slot.

Uploads are PDF, JPG, or PNG. The mock checker returns `accepted` and `reason_code`. Reason codes already used: `ok`, `no_bytes`, `format`, `not_legal_name`, `too_old`, `unsigned`, `rejected`. A rejected file stays pending. "attached" or empty bytes is `file_missing` and does not change state.

Existing error codes: `unknown_application`, `field_not_pending`, `empty_answer`, `volume_unreadable`, `phones_not_yes_or_no`, `slot_not_pending`, `file_and_missing`, `file_missing`, `answers_incomplete`, `slots_open`, `no_review`. Do not rename them. A new code needs the user to ask for that case.

## Verdict

`decide` returns the ADR §6 object with `review_id` still empty. The caller allocates. Outcomes are `RECOMMEND_GO_LIVE`, `IN_REVIEW`, and `REFUSED`. Assignees are `MERCHANT_RISK_LEAD` and `HEAD_OF_PAYMENTS`. `₹40,00,000` inclusive stays with Merchant Risk Lead. `₹40,00,001` and above is Head of Payments, and `policy_conflict_noted` is true only then.

A refused type gets `review_id` null and no assignee. A complete pack does not cure it. An unlisted type stays `IN_REVIEW` and still gets a review id. Cafe, coffee shop, and dhaba are restaurant. Kirana is grocery. A refused word wins over a kinder word.

`RECOMMEND_GO_LIVE` does not turn the shop on. There is no activate path.

The addendum is a file, and only when phones are stored. A sentence in the note is not the addendum. A note that says to activate or to ignore policy sets `injection_flagged` and does not change outcome, assignee, or review id.

`rules/` and the verifier protocol do not import the database, auth, or MCP.

## Packages

`server.py` is the process entry and stays at `src/onb/server.py`. It calls the packages. The packages do not call it.

| Path | Holds |
|---|---|
| `intake/` | What to ask next, and what a save may write |
| `rules/` | The verdict |
| `verifier/` | Document check. One class per file |
| `store/` | Application rows. One class per file |
| `clients/` | MCP client registrations. One class per file |
| `auth/` | Google sign-in. One class per file |
| `log/` | The lines Render keeps |
| `postgres/` | The database connection |

Name a new package for the work it does. Do not create `data`, `domain`, or `view`. One class per file. `decide`, `parse_volume`, `classify`, and the intake functions stay functions. Do not wrap them in an empty class. `GoogleAuthProvider` stays one object because the MCP SDK requires those methods on that object.

## Protocols

`ApplicationStore`, `DocumentVerifier`, and `ClientDirectory` are the contracts. The memory class and the Postgres class subclass the protocol on the class line, as in `class MockDocumentVerifier(DocumentVerifier)`. A structural match without the base class is not enough.

Each protocol method has a docstring that states what the caller can rely on: arguments, return value, and the case that writes nothing. Update that docstring when the contract changes.

`ClientDirectory` stores the registration of the MCP client that connects. The copilot is that client. Claude and ChatGPT are stored the same way while they talk to this server directly.

## Auth, data, logs

`/mcp` with no bearer token is HTTP 401. The challenge does not call the token invalid. `/health` stays open. Bind `0.0.0.0` and `PORT`.

The Google client id and secret stay in the environment. Do not print them, log them, or commit them. Do not add a redirect URI that is not already in `auth/redirects.py`.

One application is one jsonb snapshot row. Do not add verdict columns unless the user asks. Client registrations persist in Postgres. The MCP bearer is Google's access token. Every `/mcp` call asks Google whether that token is still valid. In-progress sign-in state and refresh handles are still memory and drop on restart. A Google access token that Google still accepts remains valid after a restart.

Log the tool, application id, error, field, slot, state, reason code, pending name, and verdict outcome. Do not log the answer, the file bytes, a token, or account or id digits.

## Tests

Run `pytest` from this repo before finishing a behavior change. A golden test names the policy clause in the assertion. Do not put an eval shop into a corpus or into this service as a new pack item.
