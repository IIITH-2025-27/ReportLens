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
| Upload (`/`) | Pick or drop one PDF, or a batch of up to 20, and upload. One PDF opens its report page. A batch uploads one after another with a status row each; ticked (default), the verifier is started on each report as it lands, and each row follows its run to the verdicts. Lists the five latest uploads. |
| Report (`/reports/:id`) | View the PDF inline or in a new tab. **Verify** runs the verifier; the results and the per-claim analysis appear below. **Run verifier again** starts a new run on the same PDF. |
| History (`/history`) | Every uploaded report, newest first, with its latest result. Search by file name. Opening one shows its earlier runs, any of which can be picked to see that analysis. **Delete** (here or on the report page) removes the report with all its runs and files. |

Every run is kept. A report page shows the latest run by default; `?run=<id>` opens an earlier one.

**Agent activity.** While a run is going, the report page lists each step as it happens, in plain words and
grouped by the sentence being checked: reading the PDF and the plan for each figure, then for each sentence
what claim was understood, which figure it was matched to (with the text-match scores), every tool call (why
that tool, what it read, whether it came from the cache or how long it took) and the verdict with its numbers
(the chart's value, the claimed value, the gap and the margin). "Show the agent's reasons" adds the reason the
agent logged for each step. Sentences with a number that are not a chart claim are not shown, here or in the
results. The verifier reports
these through an optional `on_event` listener (`chart_claim_verifier/agent/events.py`, passed to
`pipeline.verify_pdf`); the backend stores them in `run_events_v2`. The listener only reports: verdicts are the
same with or without it, and a failing listener never stops a run.

## One verifier, one database

- **Verifier.** The agent is built by `chart_claim_verifier.pipeline.build_agent` and a report is checked by
  `pipeline.verify_pdf`, the same calls `web/backend` and the CLI make. Change the verifier in the package and
  both apps pick it up.
- **Config.** The lite app runs `configs/exp/v5.yaml` (v3 plus the real-world fixes of 16 Nov, `results/run_log.md`
  section J, and two switches that send fewer claims to the TA, section K) unless `LITE_VERIFIER_CONFIG` is set. `web/backend` still uses its own `VERIFIER_CONFIG`
  (`local_real.yaml` in its `.env`). To test it, upload the reports in `sample_reports/real_world/`; each folder's
  `expected.json` says what every sentence should get.
- **Database.** The lite app uses the same database as `web/backend`. Its tables end in `_v2`
  (`reports_v2`, `verification_runs_v2`, `claim_results_v2`) and its Alembic history is kept in
  `alembic_version_v2`, so the two apps' migrations never touch each other's tables. Both `migrations/env.py`
  files leave the other app's tables out of autogenerate.
- **Settings.** `web_lite/backend/.env` is optional. Whatever it does not set (`DATABASE_URL`, `VERIFIER_*`,
  `CCV_REMOTE_*`) is read from `web/backend/.env`.

## Start and stop

```bash
./start.sh     # API on :8001 and the page on http://localhost:5174, in the background
./stop.sh
```

`start.sh` applies migrations, then starts both servers detached from the terminal (closing the terminal or the
editor does not stop them; they run until `./stop.sh` or a restart of the Mac). Logs and process ids go to
`web_lite/logs/`. Python is `$PYTHON` if set, else the first virtualenv found (`web/backend/.venv`,
`web_lite/backend/.venv`, `../chart-claim verifier/.venv`). It runs without `--reload`, so editing code does not
restart a run halfway; run `./stop.sh && ./start.sh` after a change.

**Models load at start-up** (`LITE_PRELOAD=1`, the default): about 1.5 minutes after start, `/api/health` shows
`"models": "ready"`, and from then on a report does not wait for them, however long the app has been idle. They
hold about 11 GB while the app runs. Set `LITE_PRELOAD=0` to load them on the first run instead (the memory is
then held from that run on).

On Apple silicon the models are loaded one tensor at a time (`HF_DEACTIVATE_ASYNC_LOAD=1`, set by
`chart_claim_verifier/models/vlm.py`): transformers' parallel loading deadlocks on MPS, which made the first run
hang forever at ~400% CPU.

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
| `GET` | `/api/runs/{id}/events?after=` | the agent's activity feed, oldest first; `after` = the last `seq` already shown |
| `GET` | `/api/runs/{id}/figures/{figure_id}` | a figure image extracted from the report |

Lite-only settings (`.env`): `LITE_STORAGE_DIR` (default `storage/`), `LITE_CORS_ORIGINS` (default
`http://localhost:5174`), `LITE_MAX_QUEUED_RUNS` (default 25), `LITE_PRELOAD` (default 1), `MAX_UPLOAD_MB` (default 25).

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
