# onb

The onboarding rules service for the iPe Merchant Onboarding Copilot. One Python process. No model. The copilot calls it over MCP. This process owns the application, the files, and the verdict.

The five tools are registered. `next_step` creates the application and returns the pending item plus the snapshot. `save_answer` stores the merchant's words for that one field. `save_file` stores one upload, or closes a slot the merchant does not have. The document verifier in this process is a mock. `submit` runs the rules and allocates one review id, unless the type is refused. `get_review` returns that stored verdict. It does not run the rules and it does not allocate an id.

## Layout

```
src/onb/server.py     MCP process and the five tool names
src/onb/auth.py       Google sign-in for Claude and ChatGPT
src/onb/store.py      Application rows. Postgres when `DATABASE_URL` is set, memory otherwise.
src/onb/verifier.py   Document Verifier seam, called only from this process
```

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m onb
```

`python -m onb` listens on `http://0.0.0.0:8000/mcp`. Render sets `PORT`; locally the port is 8000. `GET /health` is the health check and stays open. Ctrl+C stops it.

When `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set, `/mcp` answers 401 until the caller sends a bearer token. A call that brought no token is a sign-in challenge. The header names the discovery document and does not call the token invalid. Claude and ChatGPT open a browser, this process sends that browser to Google, and Google returns it to `/auth/google/callback`. This process then gives their app its own token. The secret stays in the environment. `ONB_PUBLIC_URL` is the public origin, with no path. On Render it defaults to `https://onb-k8ud.onrender.com`, which is the redirect already registered with Google. `GOOGLE_ALLOWED_EMAILS` is an optional comma-separated list. When it is unset, any verified Google account that passes Google's consent screen is accepted. A restart drops the sign-in. The person signs in again. The client registration is kept in Postgres, so ChatGPT can still find the client id after a restart.

Tool calls are logged to stderr. Render shows those lines on the service Logs page. The lines name the tool and the result. They do not include the merchant's answer or the file.

Cursor connects by URL, once the process is running:

```json
{
  "mcpServers": {
    "onb": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

After Render deploys the service, replace that URL with the Render URL and keep the `/mcp` path.

`render.yaml` creates the web service and a free Render Postgres database named `onb-db`. The service receives `DATABASE_URL`. Each application is one row: an id and the snapshot. Verdict columns are not designed yet. The free database expires 30 days after creation. Without `DATABASE_URL`, applications stay in memory for the life of the process.
