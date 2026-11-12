# ReportLens web app

A TA creates a course, adds students to it and releases assignments. Students upload their report to an
assignment. The TA runs the chart-claim verifier on it, checks the findings and sends back a score and a
review. A student who is asked to rework uploads a new version of the same report.

```
web/
  backend/    FastAPI + SQLAlchemy (PostgreSQL). Calls the verifier in ../chart_claim_verifier; no verifier logic is copied here.
  frontend/   React (Vite). Two portals, student and TA, chosen by the account's role.
```

## Courses and assignments

| Step | Who |
|---|---|
| Create a course | TA |
| Add students by email (one per line or comma-separated) | TA |
| Release an assignment (title, instructions, optional due date) | TA |
| Open the course, pick the assignment, upload the report | student |

- A course belongs to the TA who created it. Other TAs do not see it.
- A student sees only the courses their email was added to. An email with no account yet can be added; the
  course appears when that student signs up.
- One report per student per assignment. A report uploaded after the due date is marked late, not blocked.
- Removing a student from a course keeps the reports they already submitted.

## How a report moves

| Step | Who | Status afterwards |
|---|---|---|
| Upload a PDF | student | `submitted` |
| Run the verifier | TA | `verifying`, then `verified` (or back to `submitted` if the run fails) |
| Confirm or dismiss each finding | TA | `verified` |
| Send the review: accept, or request rework | TA | `accepted` or `rework_requested` |
| Upload a new version | student | `submitted` again |

Students never see raw verifier output. They see the TA's score and findings text, plus the findings the TA confirmed.

## Backend

Needs Python 3.10+, Tesseract, and a PostgreSQL database.

```bash
cd web/backend
python -m venv .venv && source .venv/bin/activate
pip install -U pip "setuptools>=68,<82"
pip install -r requirements.txt            # installs the verifier from the repository root in editable mode
pip install -e "../..[gpu]"                # the models the real tools need (torch, transformers, peft)
cp .env.example .env                       # then set DATABASE_URL and JWT_SECRET
alembic upgrade head                       # creates or updates the tables
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Database migrations

The schema is managed by Alembic (`migrations/`); the database URL is read from `.env`. The server does not
create tables and refuses to start on a database that has never been migrated.

```bash
alembic upgrade head                                   # apply migrations (run after every pull)
alembic revision --autogenerate -m "add x to y"        # after changing app/models.py; review the file it writes
alembic check                                          # confirms the models and the migrations agree
```

`.env` settings:

| Name | Meaning |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://user:pass@host:5432/db`) |
| `JWT_SECRET` | long random string used to sign sign-in tokens |
| `STORAGE_DIR` | where PDFs and extracted figures are kept (default `storage/`) |
| `VERIFIER_CONFIG` | experiment config, relative to the repository root (default `configs/exp/local_real.yaml`) |
| `VERIFIER_POLICY` | `informed` (default), `fixed_order`, `all_tools`, ... |
| `VERIFIER_PARSER` | `agent` (rules, then the LLM when needed; default) or `rule` |
| `CORS_ORIGINS` | origins allowed to call the API (default `http://localhost:5173`) |

The verifier uses the calibration table and tool profile that the config points to
(`calibration_tables/local/` for the default). The first run downloads and loads Qwen3-VL-4B and DePlot;
a GPU is strongly recommended.

## Frontend

```bash
cd web/frontend
npm install
npm run dev            # http://localhost:5173, /api is proxied to port 8000
```

For a deployed build set `VITE_API_URL` (see `.env.example`) and run `npm run build`.

## Accounts

Sign-up asks for the role (student or teaching assistant). Sign-in asks only for email and password; the
role stored with the account decides which portal opens. Anyone can currently sign up as a TA.

## Limits to know about

- One verifier job runs at a time, in a worker thread inside the API process. A run that is in progress when
  the server restarts is marked failed and can be started again.
- The batch check (Benjamini–Hochberg) runs over the claims of one report, not a whole assignment.
- Every query is a network round trip, so keep the backend in the same region as the database. From a machine
  far from it, pages take one to a few seconds.
- The calibration behind the verdicts was done on synthetic charts. Treat a flag as "needs a look".
