# HarnessQuest

HarnessQuest is a first-stage AI agent issue-loop platform. It deploys Langfuse as the session/trace foundation and adds an in-house FastAPI + React application for offline agent record ingestion, AI case workflow, AI-assisted log analysis, ownership management, and dashboards.

## What Is Included

- Langfuse v3 self-hosted stack.
- HarnessQuest API, worker, frontend, and business Postgres.
- MinIO object storage for raw artifacts.
- Redis queue for asynchronous AI analysis.
- Python SDK/CLI for low-intrusion session upload.
- Case console and dashboard.

## Quick Start

1. Create an environment file.

```bash
cp .env.example .env
```

2. Edit `.env` and replace secrets before any shared deployment.

At minimum, change:

- `JWT_SECRET`
- `LANGFUSE_SALT`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_ENCRYPTION_KEY`
- database and MinIO passwords

3. Start the stack.

```bash
docker compose up -d --build
```

4. Open the UIs.

- HarnessQuest: http://localhost:8080
- API health: http://localhost:8000/health
- Langfuse: http://localhost:3000
- MinIO console: http://localhost:9001

Default HarnessQuest admin:

- Email: `admin@harnessquest.local`
- Password: `admin123456`

## Upload A Sample Session

Install the SDK locally:

```bash
pip install -e sdk/python
```

Login and export the token:

```bash
harnessquest login --base-url http://localhost:8000
export HARNESSQUEST_TOKEN=...
```

Upload a JSON file:

```bash
harnessquest upload examples/sample-session.json --base-url http://localhost:8000
```

Upload an opencode session exported with the official CLI:

```bash
opencode export <sessionID> > opencode-session.json
harnessquest opencode-upload opencode-session.json --base-url http://localhost:8000
```

The web console also supports `opencode JSON` when creating a case from an uploaded session record.

Create a case from the uploaded session in the UI, or via CLI:

```bash
harnessquest case-create --title "Sample agent failure" --session-id <session_id>
```

## AI Analysis

AI analysis uses an OpenAI-compatible chat completions endpoint.

Configure:

```env
ANALYZER_BASE_URL=https://api.example.com/v1
ANALYZER_API_KEY=...
ANALYZER_MODEL=deepseek-chat
```

If the analyzer is not configured, the workflow still works and analysis returns a manual-review placeholder.

## Current Boundaries

- This stage does not force a unified model gateway.
- Offline agent records may be incomplete by design.
- Langfuse integration is optional-write: HarnessQuest stores links and tries to write a basic trace only when keys are configured.
- OIDC/OAuth variables are reserved for the next implementation pass; built-in accounts are active now.
- Database migrations are intentionally deferred for the first runnable MVP; the API creates tables on startup.
