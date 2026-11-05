# onb

The onboarding rules service for the iPe Merchant Onboarding Copilot. One Python process. No model. The copilot calls it over MCP. This process owns the application, the files, and the verdict.

The five tools are registered. `next_step` creates the application and returns the pending item plus the snapshot. `save_answer` stores the merchant's words for that one field. `save_file` stores one upload, or closes a slot the merchant does not have. The document verifier in this process is a mock. `submit` and `get_review` do not decide anything yet.

## Layout

```
src/onb/server.py     MCP process and the five tool names
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

`python -m onb` listens on `http://0.0.0.0:8000/mcp`. Render sets `PORT`; locally the port is 8000. `GET /health` is the health check. Ctrl+C stops it.

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
