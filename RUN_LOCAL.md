# Run DisputeIQ locally (no Docker, all free)

Needs Python 3.11+ and Node 20+. The database is a single SQLite file, `backend/disputeiq.db`.

## 1. One-time setup

From the project folder (`DisputeIQ`):

**Windows (PowerShell)**
```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path frontend\.env)) { Copy-Item frontend\.env.example frontend\.env }
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
cd ..\frontend
npm install
```

**Mac / Linux**
```bash
test -f .env || cp .env.example .env
test -f frontend/.env || cp frontend/.env.example frontend/.env
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cd ../frontend && npm install
```

Open `.env` and paste your free key from https://aistudio.google.com/apikey after `GEMINI_API_KEY=`.

## 2. Start it (every time)

Terminal 1, backend:
```powershell
cd backend
.venv\Scripts\activate          # Mac/Linux: . .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Terminal 2, frontend:
```powershell
cd frontend
npm run dev
```

Open http://localhost:5173 and sign in with the reviewer key from `REVIEWER_ACCOUNTS` in your `.env`
(see README). Without that setting the API refuses case, customer and metrics requests.

## How the data works

* **Default behavior:** demo bootstrap is disabled. The backend will not automatically populate an empty database.
* **Optional fresh demo setup:** for a brand-new, empty, isolated demo database only, set `BOOTSTRAP_DEMO_DATA=true` in `.env` before starting the backend. Bootstrap runs in the background using the offline rule engine, without consuming Gemini quota.
* **Existing database:** leave `BOOTSTRAP_DEMO_DATA=false`. Existing complaints and reviews must be preserved.
* The backend uses `backend/disputeiq.db`, regardless of the folder from which you start it.
* Never delete an existing database just to refresh demo data. Back it up and use a separate empty demo database if a fresh dataset is required.
* Do not run `python -m data_gen.seed --reset` against a database you want to keep; it deletes data.

## Check Gemini works
```powershell
cd backend
python -m app.agent.cli --ping-llm
```
If the key is missing or the free quota is used up, a submitted complaint still saves; it goes to
"Needs review" with the error shown in its audit trail (the app never fakes AI output).

## Tests
```powershell
cd backend; $env:LLM_PROVIDER="mock"; pytest -q
cd ..\frontend; npm test; npm run build
```

## Troubleshooting
* "Cannot reach the API": the backend is not running, or `frontend/.env` `VITE_API_URL` is not
  `http://localhost:8000`.
* Queue empty right after the very first start: wait 20 seconds and refresh, or pick the "All" tab.
* Port in use: change `--port` and `VITE_API_URL` together.
