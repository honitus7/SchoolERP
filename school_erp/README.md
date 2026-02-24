# School ERP (Flask + SQLite + AI Copilot)

Full-scale school/coaching ERP monolith with:
- Roles: `admin`, `teacher`, `parent`, `student`
- Flask SSR UI (Jinja components + HTMX) with per-module API console
- REST API under `/api/v1`
- SQLite persistence (WAL mode)
- AI copilot with risk-based approval queue
- Enterprise modules (admissions, transport, payroll, library, hostel, inventory, coaching)

## Stack
- Flask 3
- SQLAlchemy + Flask-Migrate
- Flask-JWT-Extended
- Flask-WTF + CSRF
- APScheduler
- OpenAI API integration (optional key)

## Project Layout
- `run.py`: local server entry
- `app/`: application package
- `app/models/`: tenant-ready schema
- `app/services/`: business logic
- `app/blueprints/`: role/module web and API routes
- `app/templates/components/`: reusable UI components
- `app/ai/`: copilot client, policy, execution
- `app/tasks/`: scheduler/OCR/PDF helpers
- `app/tests/`: unit/integration/e2e tests

## Setup
```bash
cd school_erp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app app.wsgi seed
python run.py
```

App URL: `http://127.0.0.1:5000`

## SQLite Cloud Notes
- Use `DATABASE_URL` in the format: `sqlitecloud://host:port/database_name.sqlite?apikey=...`
- If your URL does not include the database path, set `SQLITECLOUD_DB=database_name.sqlite`.
- If you see `USE DATABASE command` errors, your database name/path is missing from the connection setup.

## Production Run
```bash
cd school_erp
source .venv/bin/activate
gunicorn -c gunicorn.conf.py app.wsgi:app
```

Health endpoint: `GET /api/v1/health`

## Seeded Users
- `admin / admin123`
- `teacher / teacher123`
- `parent / parent123`
- `student / student123`

## Key API Endpoints
- Auth: `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/refresh`
- Dashboard: `GET /api/v1/dashboard/{role}`
- Attendance: `POST /api/v1/attendance/sessions`, `POST /api/v1/attendance/sessions/{id}/records`, `POST /api/v1/attendance/teacher-self`, `GET /api/v1/attendance/teacher-self`, `GET /api/v1/attendance/students/{student_id}/summary`, `GET /api/v1/attendance/my-summary`, `GET /api/v1/attendance/my-records`, `POST /api/v1/attendance/ocr/import`
- OCR review/commit: `GET /api/v1/attendance/ocr/batches`, `GET /api/v1/attendance/ocr/batches/{id}`, `POST /api/v1/attendance/ocr/batches/{id}/commit`
- Exams: `POST /api/v1/exams`, `GET /api/v1/exams`, `GET /api/v1/exams/{id}/overview`, `GET /api/v1/exams/{id}/marks`, `POST /api/v1/exams/{id}/schedule`, `POST /api/v1/exams/{id}/marks`, `POST /api/v1/exams/{id}/publish`, `GET /api/v1/exams/my-results`
- Report cards: `GET /api/v1/report-cards`, `GET /api/v1/report-cards/{student_id}`, `GET /api/v1/report-cards/{student_id}/pdf`
- Fees: `POST /api/v1/fees/structures`, `POST /api/v1/fees/installments`, `POST /api/v1/fees/receipts`, `GET /api/v1/fees/{student_id}/dues`
- Notices/Events/Reminders/Calendar: `POST/GET /api/v1/notices`, `POST/GET /api/v1/events`, `POST /api/v1/reminders`, `GET /api/v1/calendar`
- Messaging: `POST /api/v1/messages/threads`, `POST /api/v1/messages/threads/{id}/messages`, `GET /api/v1/messages/threads/{id}/messages?since=...`
- AI: `POST /api/v1/ai/chat`, `GET /api/v1/ai/actions/pending`, `POST /api/v1/ai/actions/{id}/approve`, `POST /api/v1/ai/actions/{id}/reject`
- Directory: `GET /api/v1/directory/classes|students|subjects|users`
- Extended enterprise: admissions status patch, transport vehicles/stops, payroll entries, library loans, hostel hostels, inventory stock-moves, coaching batches/test-series/test-attempts

Role safety:
- Web and API dashboards enforce role-specific access.
- Parent/student data access is scoped to linked student profiles for fees and report cards.
- Parent/student class and exam listings are scoped to their linked student enrollments.
- Notices are audience-scoped (`all`, `teacher`, `parent`, `student`), and reminders/calendar entries are filtered by role visibility.

AI copilot behavior:
- Customer-facing answers are phrased in product language (no raw API/DB output).
- Prompt routing can trigger workflows (notice/reminder/event) using natural language.
- Risk policy is enforced through approval states (`pending` vs `executed`).

## Tests
```bash
cd school_erp
source .venv/bin/activate
pytest -q
```

Current status: all tests passing.
