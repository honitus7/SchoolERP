# School ERP (Flask + SQLite + AI Copilot)

Full-scale school/coaching ERP monolith with:
- Roles: `admin`, `teacher`, `parent`, `student`
- Flask SSR UI (Jinja components + HTMX)
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

## Seeded Users
- `admin / admin123`
- `teacher / teacher123`
- `parent / parent123`
- `student / student123`

## Key API Endpoints
- Auth: `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/refresh`
- Dashboard: `GET /api/v1/dashboard/{role}`
- Attendance: `POST /api/v1/attendance/sessions`, `POST /api/v1/attendance/sessions/{id}/records`, `POST /api/v1/attendance/ocr/import`
- Exams: `POST /api/v1/exams`, `POST /api/v1/exams/{id}/schedule`, `POST /api/v1/exams/{id}/marks`, `POST /api/v1/exams/{id}/publish`
- Report cards: `GET /api/v1/report-cards/{student_id}`, `GET /api/v1/report-cards/{student_id}/pdf`
- Fees: `POST /api/v1/fees/structures`, `POST /api/v1/fees/installments`, `POST /api/v1/fees/receipts`, `GET /api/v1/fees/{student_id}/dues`
- Notices/Events/Reminders/Calendar: `POST/GET /api/v1/notices`, `POST/GET /api/v1/events`, `POST /api/v1/reminders`, `GET /api/v1/calendar`
- Messaging: `POST /api/v1/messages/threads`, `POST /api/v1/messages/threads/{id}/messages`, `GET /api/v1/messages/threads/{id}/messages?since=...`
- AI: `POST /api/v1/ai/chat`, `GET /api/v1/ai/actions/pending`, `POST /api/v1/ai/actions/{id}/approve`, `POST /api/v1/ai/actions/{id}/reject`

## Tests
```bash
cd school_erp
source .venv/bin/activate
pytest -q
```

Current status: all tests passing.
