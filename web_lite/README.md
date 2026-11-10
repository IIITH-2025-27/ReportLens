# ReportLens Lite

A small, open version of the ReportLens web app for TAs: no sign-in, no accounts. Upload a report, press
Verify, and read the chart-claim verifier's results on the same page.

```
web_lite/
  backend/    FastAPI + SQLAlchemy. Calls the verifier in ../chart_claim_verifier; no verifier logic is copied here.
  frontend/   React (Vite). Three pages: Upload, History, Report. Uses web/frontend's stylesheet.
```

## Pages

| Page | What it does |
|---|---|
| Upload (`/`) | Pick or drop a PDF and upload it. Lists the five latest uploads. |
| Report (`/reports/:id`) | View the PDF inline or in a new tab. **Verify** runs the verifier; the results and the per-claim analysis appear below. **Run verifier again** starts a new run on the same PDF. |
| History (`/history`) | Every uploaded report, newest first, with its latest result. Search by file name. Opening one shows its earlier runs, any of which can be picked to see that analysis. **Delete** (here or on the report page) removes the report with all its runs and files. |

Every run is kept. A report page shows the latest run by default; `?run=<id>` opens an earlier one.

## One verifier, one database

- **Verifier.** The agent is built by `chart_claim_verifier.pipeline.build_agent` and a report is checked by
  `pipeline.verify_pdf`, the same calls `web/backend` and the CLI make. Change the verifier in the package and
  both apps pick it up.
- **Database.** The lite app uses the same database as `web/backend`. Its tables end in `_v2`
  (`reports_v2`, `verification_runs_v2`, `claim_results_v2`) and its Alembic history is kept in
  `alembic_version_v2`, so the two apps' migrations never touch each other's tables. Both `migrations/env.py`
  files leave the other app's tables out of autogenerate.
- **Settings.** `web_lite/backend/.env` is optional. Whatever it does not set (`DATABASE_URL`, `VERIFIER_*`,
  `CCV_REMOTE_*`) is read from `web/backend/.env`.

## Backend

Needs Python 3.10+, Tesseract, and the database the full web app uses (or any other PostgreSQL database).

```bash
cd web_lite/backend
python -m venv .venv && source .venv/bin/activate      # or reuse web/backend/.venv: it has everything
pip install -U pip "setuptools>=68,<82"
pip install -r requirements.txt            # installs the verifier from the repository root in editable mode
pip install -e "../..[gpu]"                # the models the real tools need (torch, transformers, peft)
cp .env.example .env                       # optional, see above
alembic upgrade head                       # creates the _v2 tables
uvicorn app.main:app --reload --port 8001
```

API docs: http://localhost:8001/docs

| Method | Path | |
|---|---|---|
| `POST` | `/api/reports` | upload a PDF (form field `file`) |
| `GET` | `/api/reports?q=` | history, newest first |
| `GET` | `/api/reports/{id}` | one report and its runs |
| `GET` | `/api/reports/{id}/pdf` | the PDF, inline |
| `DELETE` | `/api/reports/{id}` | delete the report, its runs and claims, the PDF and the figures (refused while a run is active) |
| `POST` | `/api/reports/{id}/verify` | start a new run |
| `GET` | `/api/runs/{id}` | a run with its claims and figures |
| `GET` | `/api/runs/{id}/figures/{figure_id}` | a figure image extracted from the report |

Lite-only settings (`.env`): `LITE_STORAGE_DIR` (default `storage/`), `LITE_CORS_ORIGINS` (default
`http://localhost:5174`), `LITE_MAX_QUEUED_RUNS` (default 10), `MAX_UPLOAD_MB` (default 25).

## Frontend

```bash
cd web_lite/frontend
npm install
npm run dev            # http://localhost:5174, /api is proxied to port 8001
```

For a deployed build set `VITE_API_URL` (see `.env.example`) and run `npm run build`.

## Limits to know about

- Open to everyone: anyone with the link can upload, verify, and open every report in the history. Do not put
  it on the public internet without something in front of it (a VPN, basic auth at the proxy, ...).
- One verifier job runs at a time, in a worker thread inside the API process, and at most
  `LITE_MAX_QUEUED_RUNS` wait at once. If the full web app runs on the same machine, each process loads its own
  copy of the models. A run in progress when the server restarts is marked failed and can be started again.
- The calibration behind the verdicts was done on synthetic charts. Treat a flag as "needs a look".
