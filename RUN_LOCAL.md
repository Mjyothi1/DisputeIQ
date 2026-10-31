# Run DisputeIQ without Docker (Antigravity / any IDE terminal)

Needs only Python 3.11+ and Node 20+. The database is a local SQLite file, nothing to install.
(SQLite mode skips pgvector similar-case retrieval; everything else is identical.)

## 1. Backend (terminal 1)
```bash
cd disputeiq
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
```
Open `.env` and swap the database lines: comment out the `postgresql+psycopg://...` DATABASE_URL and
uncomment `DATABASE_URL=sqlite:///./disputeiq.db`. Then:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m app.db.init_db
python -m data_gen.seed --seed 42 --anchor 2026-10-27 --reset
uvicorn app.main:app --reload --port 8000
```
Check http://localhost:8000/health and http://localhost:8000/docs

## 2. Frontend (terminal 2)
```bash
cd disputeiq/frontend
cp .env.example .env            # Windows: Copy-Item .env.example .env
npm install
npm run dev
```
Open http://localhost:5173 and type your name in the header.

## 3. Fill the queue (terminal 3, in `backend`, venv active)
Seeded cases start as "New". Process the 100 held-out cases and write the evaluation report:
```bash
python -m eval.run_eval
```
Or use "Submit complaint" in the UI to run a single new case.

## 4. Gemini Flash (default LLM)
In `.env`: `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=<free-tier key from Google AI Studio>`,
`GEMINI_MODEL=gemini-3.8-flash` (optional override). The key is backend-only — never put it in
`frontend/.env`. For offline pytest only, set `LLM_PROVIDER=mock` explicitly; API failures never
silently switch to mock.

Verify: `python -m app.agent.cli --ping-llm`

LLM-written complaints: re-seed with `python -m data_gen.seed --seed 42 --anchor 2026-10-27 --reset --llm`.
Langfuse: `pip install -e ".[langfuse]"` and set `LANGFUSE_ENABLED=true` + keys.

## 5. Tests
```bash
cd backend && pytest -q && ruff check . && mypy app
cd ../frontend && npm test && npm run build
```

## Troubleshooting
- Browser shows "Cannot reach the API": backend not running, or `frontend/.env` VITE_API_URL differs from the backend port.
- Blank queue: choose the "All" tab, or run step 3.
- Port in use: change `--port` and `VITE_API_URL` together.
- Docker later (optional): `docker compose up --build -d`, then seed via `docker compose exec backend ...`.
