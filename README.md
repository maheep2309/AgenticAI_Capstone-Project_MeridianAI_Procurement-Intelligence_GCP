# Meridian AI: Procurement Intelligence on Google Cloud

**Agentic AI capstone using Langchain**

Meridian AI helps a finance team review procurement requests before payment and get answers from its own policy documents. It combines a **multi-agent audit pipeline** with a **RAG document Q&A service**, runs on a laptop with a single Gemini API key, and deploys to **Google Cloud Run** with **Vertex AI Vector Search** through a GitHub Actions pipeline.

> All company data in this repository (*Aldermoor Industries*, its vendors and documents) is **fictional**. The agents' sanctions, credit and tax checks are produced by the LLM, not by authoritative data sources; only the FX-rate check calls a live API. This is a working prototype of the architecture, not a compliance tool.

The business case, requirements and evaluation are in the [Business Report](Business%20Report/MeridianAI_Business_Report.pdf).

---

## The problem

Procurement approvals in a mid-sized manufacturer involve several specialists (compliance, treasury/tax, financial control) and a final sign-off by the CFO. Each reviewer has to dig through policies, tariff schedules and accounting rules. Reviews are slow, inconsistent and hard to audit afterwards.

## What Meridian AI does

| Capability | How it works |
|---|---|
| **Purchase-request audit** | Three specialist agents review the request in sequence: **Risk & Compliance** (sanctions screening, vendor credit), **Tax & Treasury** (cross-border tax, FX-rate validation against a live rate) and **Financial Control** (expense categorisation, approval thresholds). A **CFO synthesis** step then writes one memo with a final decision: `APPROVED TO PAY`, `CONDITIONAL HOLD` or `REJECTED`. |
| **Document Q&A (RAG)** | Upload PDFs (policies, annual reports, tariff schedules) and ask questions in plain English. Answers are grounded only in the retrieved chunks and cite their source. Three retrieval strategies: `similarity` (default), `multiquery` and `contextual` compression. |
| **Guard-rails** | LangChain v1 middleware around every agent: PII redaction (e-mails, card numbers), model- and tool-call limits, retries with back-off, and a structured log line per tool call. |
| **Local / cloud toggle** | One setting, `APP_MODE`, switches storage between a local Chroma database and Vertex AI Vector Search + Cloud Storage. No other code changes. |

---

## Architecture

```
 Browser (React + TypeScript)
    │  REST /api/*
    ▼
 FastAPI backend ──────────────────────────────────────────────────────────┐
    │                                                                      │
    ├─ /api/agent/audit ─► ProcurementSupervisor                           │
    │                        Risk agent    ─ tools: sanctions, credit      │
    │                        Tax agent     ─ tools: cross-border tax, FX ──┼─► Frankfurter FX API
    │                        Control agent ─ tools: expense category       │
    │                        CFO synthesis ─► final memo                   │
    │                      (all wrapped in middleware guard-rails)         │
    │                                                                      │
    └─ /api/rag/*  ─► PDF → chunks → embeddings → vector store ◄─ retrieve ┘
                                                     │
                       APP_MODE=local                │  APP_MODE=cloud
                       Chroma (.meridian/chroma)     │  Vertex AI Vector Search
                       .meridian/uploads             │  Cloud Storage bucket
                                                     ▼
                                               Gemini (answers)
```

Package dependencies flow one way only: `api → rag, agent → config, logger, exceptions`.

### Local vs cloud mode

| | `APP_MODE=local` (default) | `APP_MODE=cloud` |
|---|---|---|
| Chat model | Gemini API (`GOOGLE_API_KEY`) | Gemini API (key injected from Secret Manager) |
| Embeddings | `gemini-embedding-001` via Gemini API, 768 dims | `text-embedding-005` via Vertex AI, 768 dims |
| Vector store | Chroma on disk (`.meridian/chroma`) | Vertex AI Vector Search (stream updates) |
| Uploaded PDFs | `.meridian/uploads/` | `gs://<project>-vector-staging/uploads/` |
| Logs | `logs/` (JSON lines) | stdout → Cloud Logging, plus a copy to the bucket on shutdown |
| GCP project needed | No | Yes |

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| API | FastAPI, Pydantic, Uvicorn |
| LLM orchestration | LangChain v1 (`create_agent`, agent middleware, LCEL), LangGraph runtime |
| Models | Google Gemini (chat), Gemini / Vertex AI text embeddings |
| Vector stores | Chroma (local), Vertex AI Vector Search (cloud) |
| Storage & secrets | Google Cloud Storage, Secret Manager |
| Runtime & delivery | Docker (multi-stage), Cloud Run, Cloud Build, GitHub Actions |
| Observability | structlog JSON logs with Cloud Logging `severity` field |
| Testing | pytest (backend, with fake LLMs), Vitest (frontend) |

---

## Repository structure

```
backend/
├── api/
│   ├── main.py               App factory, error handlers, serves the built React app
│   ├── endpoints.py          REST routes (/api/health, /api/status, /api/agent/*, /api/rag/*)
│   └── schemas.py            Pydantic request/response models
├── agent/
│   ├── agents.py             ProcurementSupervisor: runs risk → tax → control → CFO
│   ├── tools.py              Five agent tools (sanctions, credit, tax, FX, expense category)
│   ├── prompts.py            System prompts for each specialist and the CFO memo
│   └── middleware.py         PII redaction, call limits, retries, tool-call logging
├── rag/
│   ├── llm.py                Gemini chat model
│   ├── embeddings.py         Embedding model (follows APP_MODE)
│   ├── vector_store.py       Chroma or Vertex AI Vector Search (follows APP_MODE)
│   ├── document_store.py     Original PDFs: local folder or GCS bucket
│   ├── data_ingestion.py     PDF → chunks → vector store
│   └── retrieval.py          Retrieval strategies and the RAG chain
├── config/settings.py        All settings, read from environment / .env
├── logger/custom_logger.py   Structured JSON logging
├── exceptions/               ConfigurationError, IngestionError
└── tests/                    17 offline tests (no API key or internet needed)

frontend/                     React app; src/lib/api.ts is the only file that calls the backend
sample_uploaded_docs/         Four fictional PDFs for trying document Q&A
Business Report/              Business case, requirements and evaluation (PDF)
.github/workflows/deploy.yml  Provisions GCP resources and deploys to Cloud Run
generate_json.py              Writes the one bootstrap vector needed to create the Vector Search index
Dockerfile                    Multi-stage build: React app + FastAPI in one image
requirements.txt              Runtime Python packages, pinned (used by Docker)
requirements-dev.txt          Runtime + tests, notebooks and dev tools (used locally)
pyproject.toml / uv.lock      Project metadata and locked versions for uv
.env.example                  Template for local settings
DEPLOY_GCP.md                 Step-by-step Google Cloud deployment guide
```

---

## Run locally

**Prerequisites:** Python 3.12, Git, Node.js 20+ (for the web UI) and a Gemini API key from https://aistudio.google.com/apikey.

```bash
git clone https://github.com/maheep2309/AgenticAI_Capstone-Project_MeridianAI_Procurement-Intelligence_Langchain_GCP.git meridian-ai
cd meridian-ai

python3.12 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt    # or: uv sync

cp .env.example .env                   # Windows: copy .env.example .env
# edit .env and set GOOGLE_API_KEY=... (keep APP_MODE=local)

uvicorn api.main:app --app-dir backend --reload --port 8080
```

Run every command from the project root. The interactive API docs are at **http://localhost:8080/docs**.

**Web UI** (second terminal, backend still running):

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

### Try it

**Audit:** `POST /api/agent/audit` with:

```json
{"request_text": "Purchase of 200 PLC controllers from Takumi Controls Europe B.V. (Netherlands). Total 480,000 EUR. Origin JP, destination DE. FX rate quoted: 1 EUR = 163.5 JPY."}
```

The response has four fields: `risk_result`, `tax_result`, `control_result` and `cfo_memo`. Several LLM calls run in sequence, so expect up to a minute.

**Document Q&A:** upload the PDFs in `sample_uploaded_docs/` (Index Documents tab or `POST /api/rag/upload`), then ask:

| Question | Expected answer |
|---|---|
| What is Aldermoor Industries' total revenue in FY2024? | About EUR 2.84 billion |
| What are the payment terms for servo motor suppliers? | Net-45 |
| What is the customs duty on PLC controllers from Japan? | 2.2 % |
| Over how many years is filling line equipment depreciated? | 10 years |

A question the documents do not cover should get an "I don't know" style answer.

### API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness check, returns `{"status": "ok", "mode": "<local or cloud>"}` |
| GET | `/api/status` | Active mode, models and storage locations |
| POST | `/api/agent/audit` | Run the four-step procurement audit |
| POST | `/api/rag/upload` | Upload one or more PDFs and index them |
| GET | `/api/rag/uploads` | Upload history (in memory, resets on restart) |
| POST | `/api/rag/ingest` | Re-index every PDF already in the document store |
| POST | `/api/rag/ask` | Ask a question (`retriever_type`: `similarity`, `multiquery`, `contextual`) |

### Tests

```bash
pytest backend/tests               # expected: 17 passed
cd frontend && npm test            # Vitest
```

The backend tests use fake LLMs and a temporary Chroma folder, including a full local PDF → Chroma → answer run and an agent run through the middleware, so they need no API key or internet.

### Docker

```bash
docker build -t meridian-ai .
docker run -p 8080:8080 --env-file .env -v "$(pwd)/.meridian:/app/.meridian" meridian-ai
```

Open http://localhost:8080. The image never contains `.env`; it is passed at run time. The volume keeps the local vector store and uploads between runs.

---

## Deploy to Google Cloud

Pushing to `main` runs [.github/workflows/deploy.yml](.github/workflows/deploy.yml). In order, it:

1. Enables the required Google Cloud APIs.
2. Creates the `<project>-vector-staging` bucket.
3. Uploads a bootstrap vector (`generate_json.py`), then creates the Vector Search index and endpoint and deploys the index.
4. Stores the Gemini key in Secret Manager and grants the Cloud Run service account its runtime roles.
5. Builds the image with Cloud Build and deploys it to Cloud Run.

The first run takes 30–60 minutes, mostly for Vector Search provisioning. The full setup, including service accounts, required IAM roles, costs and tear-down, is in **[DEPLOY_GCP.md](DEPLOY_GCP.md)**.

> **Cost warning:** a deployed Vector Search index is billed per hour even when idle. Undeploy it when you are not using it (see DEPLOY_GCP.md).

---

## Configuration

Settings are read from environment variables, or from `.env` locally ([backend/config/settings.py](backend/config/settings.py)). `.env` is git-ignored.

| Variable | Default | Used in |
|---|---|---|
| `APP_MODE` | `local` | Always (`local` or `cloud`) |
| `ENVIRONMENT` | `local` | Label only (`production` on Cloud Run) |
| `GOOGLE_API_KEY` | (none) | Both modes (Gemini chat; embeddings in local mode) |
| `VERTEX_LLM_MODEL_NAME` | `gemini-3.8-flash` | Chat model |
| `LLM_TEMPERATURE` | `0.0` | Chat model |
| `LOCAL_EMBEDDING_MODEL_NAME` | `gemini-embedding-001` | Local mode |
| `LOCAL_DATA_DIR` | `./.meridian` | Local mode (Chroma + uploads) |
| `CHROMA_COLLECTION` | `meridian_docs` | Local mode |
| `AGENT_MAX_MODEL_CALLS` / `AGENT_MAX_TOOL_CALLS` / `AGENT_MAX_RETRIES` | `8` / `6` / `2` | Agent middleware |
| `GCP_PROJECT_ID` | (none) | Cloud mode |
| `GCP_REGION` | `us-central1` | Cloud mode |
| `GCS_BUCKET_NAME` | (none) | Cloud mode (`<project>-vector-staging`) |
| `GCS_PREFIX` | `uploads/` | Cloud mode |
| `VECTOR_SEARCH_INDEX_ID` / `VECTOR_SEARCH_INDEX_ENDPOINT_ID` | (none) | Cloud mode |
| `VERTEX_EMBEDDING_MODEL_NAME` | `text-embedding-005` | Cloud mode |
| `GCP_SERVICE_ACCOUNT_PATH` | (none) | Cloud mode from a laptop only. If the file exists it is used instead of `gcloud auth application-default login`. |

Gemini model names are retired over time. If you get "model not found", set `VERTEX_LLM_MODEL_NAME` to a current model from https://ai.google.dev/gemini-api/docs/models.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'api'` | Start from the project root with `--app-dir backend` |
| `ModuleNotFoundError` for another package | Activate `.venv` and run `pip install -r requirements-dev.txt` |
| Settings appear empty | `.env` must be in the project root |
| `503` "APP_MODE=cloud but these settings are empty" | Fill in the listed cloud settings, or set `APP_MODE=local` |
| `503` "GOOGLE_API_KEY is empty" | Add the key to `.env` and restart |
| Stale answers after replacing documents | Local mode: delete `.meridian/` and upload again |
| `403` from Google Cloud | Missing IAM role or wrong credentials; see the troubleshooting table in [DEPLOY_GCP.md](DEPLOY_GCP.md) |
| Browser shows a CORS error | The backend is not running on port 8080 |

---

## Limitations and next steps

- Sanctions, credit and tax figures come from the LLM's general knowledge. The next step is to connect authoritative sources (sanctions lists, credit bureaus, tariff databases) as tools.
- The Cloud Run service is public and has no authentication. Add Identity-Aware Proxy or an auth layer before using real data.
- Upload history is kept in memory. Persist it (for example Firestore) to survive restarts.
- Move the chat model to Vertex AI with Application Default Credentials, so cloud mode needs no API key.

---

*Author: Maheep. Aldermoor Industries and all sample data are fictional.*
