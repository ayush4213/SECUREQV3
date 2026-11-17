# SecurePaper — Version 3 Examination Portal

A student-and-teacher examination management web application built by upgrading the existing SecurePaper FastAPI + SQLite project. It keeps the existing **tagged MCQ question bank**, verified correct options, and wrong-answer pools; it adds account authentication, teacher-assigned paper sets, exam schedules, student practice, and results.

## What you can do

| Student portal | Teacher portal |
| --- | --- |
| Sign in using a unique roll number and password | Sign in with teacher email and password |
| Create self-practice tests by subject/topic, optionally choosing specific questions | Create/deactivate students, edit roll numbers and reset student passwords |
| See assigned papers with upcoming, available, and completed statuses | View and manage the existing question bank, add questions and import JSON |
| View the animated locked-paper screen before the scheduled start | Create exam schedules, marking rules and multiple distinct paper sets |
| Start at the scheduled opening, answer four-option MCQs, move between questions | Assign Set A/B/C/etc. to roll numbers manually or automatically |
| Autosave answers, submit or finish when the examination time expires | Track student completion, scores, percentages and detailed answer reviews |
| View practice results immediately and teacher-exam answer reviews after the exam window ends | Export test-wise reports as CSV or XLSX |

The examination screen visually simulates a secured paper before the scheduled start. **Backend authorization**, not the animation, enforces the actual opening time and assignment rules. The app selects MCQs from the stored database and does not generate new question text.

## Start locally (Python)

Python 3.10+ is required (3.12 recommended).

```bash
cd securepaper
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\\Scripts\\activate
pip install -r requirements.txt

# Supply initial teacher credentials BEFORE the first run:
export SECUREPAPER_TEACHER_EMAIL=teacher@securepaper.local
export SECUREPAPER_TEACHER_PASSWORD='use-a-long-unique-password'

uvicorn backend.main:app --reload
```

Open **http://127.0.0.1:8000**. Select **Teacher Login**, use the email and password above, and create students under **Student management**. Students then select **Student Login** and use their assigned roll numbers and passwords. Only teachers can create student accounts.

On initial startup, the database is **migrated in place** and the first teacher is bootstrapped from environment variables. If those variables are absent but `SECUREPAPER_ADMIN_KEY` is set on an older deployment, that existing secret is accepted as the initial teacher password; the default email is `teacher@securepaper.local`. Existing teacher passwords are *not* silently overwritten on later restarts.

To reset an existing teacher account intentionally, use **Account settings** in the website or, as a server operator:

```bash
python -m scripts.reset_teacher_password --email teacher@securepaper.local
```

The command prompts for a new password unless `SECUREPAPER_TEACHER_PASSWORD` is set.

## Run using Docker Compose

```bash
cp .env.example .env
# Edit .env and set a private SECUREPAPER_TEACHER_PASSWORD.
docker compose up --build -d
```

The web app is available at **http://localhost:8000**. Its SQLite database is stored in the `securepaper_data` Docker named volume. Do not remove that volume when rebuilding.

## Update an existing Render service

Read **[RENDER_UPDATE_GUIDE.md](RENDER_UPDATE_GUIDE.md)** before deploying. The essential points are:

1. Deploy this code into the **existing Render service** that owns `https://secure-ques-q.onrender.com/`, rather than creating a new web service and losing the existing volume mapping.
2. Keep the current `SECUREPAPER_DATA_DIR` unchanged and keep its persistent disk mounted. The database migration happens automatically at startup.
3. Provide `SECUREPAPER_TEACHER_PASSWORD` and optionally `SECUREPAPER_TEACHER_EMAIL` for first teacher creation. Existing `SECUREPAPER_ADMIN_KEY` can be used as a fallback for first-time bootstrap if already configured.
4. Keep the same start command: `./start.sh`, or Docker deploy using the supplied `Dockerfile`.
5. Confirm `/api/health` returns `{"status":"ok","version":"3",...}` and `teacher_configured: true`.

**Do not replace your live `securepaper.db` with the example DB in this ZIP**. The included `data/securepaper.db` is a snapshot of the previously supplied bank, not a copy of any changes made later on Render. Back up the live database before upgrading. On a server with access to the existing data path:

```bash
python -m scripts.backup_db /path/to/backups/securepaper-before-v3.db
```

## Create a teacher examination

1. In **Student management**, create student accounts. Roll numbers must be unique across the database.
2. Open **Create examination**. Enter the examination name, subject, optional topic, question count, duration, marks per question, optional negative marks, and scheduled local start time.
3. Choose 1–6 paper sets, labelled A–F. In **Automatic sets**, the app forms distinct combinations from the selected subject/topic bank (optionally restricted to a manually chosen pool). When inventory permits, sets have no questions in common. In **Choose per set**, pick exactly the requested question count for each set.
4. Assign specific roll numbers, one per line, either `101` (automatic A/B/C rotation) or `101,A` (manual set). You may upload a CSV/text list; see `samples/roll_assignments.csv`.
5. Press **Create Test**. The only creation confirmation is: **Test successfully saved.**

The system rejects unknown/deactivated roll numbers, duplicates in an assignment request, invalid set labels, and insufficient question inventory. The entire exam, its sets and its assignments are stored in one database transaction.

## Scheduling and results rules

- Before a scheduled exam starts, students receive only assignment metadata and the locked-paper screen. The actual questions are unavailable from assigned-paper APIs until the exam starts.
- Scheduled exams have one fixed examination window: **start time through start time + duration**. A student joining late has only the remaining time. After that window, new attempts cannot begin.
- An already-started attempt is automatically finalized on its deadline by a server-side periodic check and again on any subsequent request. The browser also submits when its countdown reaches zero.
- A student can submit early. Their marks are visible after submission. Detailed correct answers for a **teacher examination** become visible to students only when the scheduled window ends; teachers may review their examination results at any time.
- Self-practice starts immediately after creation. Students may review practice answers after submission. Questions reserved for unfinished teacher examinations are excluded from *new* student practice selections and student question-picker results.
- Marks are calculated as `correct × marks_per_question − incorrect × negative_marks`. Unanswered questions contribute zero.
- All student attempt and assignment routes verify the identity obtained from an authenticated, HTTP-only session cookie. They do not accept a roll number from the frontend as proof of access.

## Existing question bank

Questions are still in the original SQLite `questions` and `question_options` tables, with `subject`, `topic`, `difficulty`, `question_type`, a single verified correct answer and 3–30 associated wrong options. Each attempt picks one correct option plus three random wrong options and independently shuffles their positions. Imported question markers are never sent to students during an active attempt.

The included `seed/seed_questions.json` contains the 90 previously supplied questions and is used **only if the question table is empty**. Existing rows and option IDs remain unchanged. The previous `exam_sessions` tables remain in the database for historical preservation; their anonymous v2 endpoints are retired to enforce the new authenticated access controls. The old source is archived in `legacy/version2/`.

## Important API routes

| Method | Route | Access |
| --- | --- | --- |
| POST | `/api/v3/auth/login` | Student or teacher |
| GET | `/api/v3/auth/me` | Signed-in user |
| POST | `/api/v3/auth/logout` | Signed-in user |
| POST | `/api/v3/auth/password` | Signed-in user |
| GET | `/api/v3/catalog` | Signed-in user |
| GET | `/api/v3/questions` | Signed-in user (no correct-answer markers) |
| GET | `/api/v3/student/dashboard` | Student |
| POST | `/api/v3/student/practice` | Student |
| GET | `/api/v3/student/assignments/{id}` | Assigned student |
| POST | `/api/v3/student/assignments/{id}/start` | Assigned student, within exam window |
| GET/POST | `/api/v3/student/attempts/{id}` and `/answer`, `/submit` | Attempt owner |
| GET | `/api/v3/student/results/{id}` | Attempt owner, submitted |
| GET/POST/PATCH | `/api/v3/teacher/students...` | Teacher |
| GET/POST | `/api/v3/teacher/exams...` | Teacher who owns the exam |
| GET | `/api/v3/teacher/exams/{id}/results` | Exam owner |
| GET | `/api/v3/teacher/exams/{id}/export?format=csv\|xlsx` | Exam owner |
| GET/POST/PATCH | `/api/v3/teacher/questions...` | Teacher |

State-changing authenticated requests use an `X-CSRF-Token` header supplied by `/api/v3/auth/login` or `/api/v3/auth/me`. Auth tokens are random and stored only as SHA-256 hashes in the database; browser cookies are HTTP-only and `Secure` when served over HTTPS. Passwords use PBKDF2-HMAC-SHA256 with per-account salts. Protected resources use database-backed, role-scoped authorization.

## Tests

```bash
python -m pytest -q tests/
```

The regression suite checks migration from the original database, student isolation, roll uniqueness, question shuffling, safe auto-submission, scheduled locking, distinct paper sets, negative marking, result release rules, teacher ownership, batch assignment, CSV/XLSX export, CSRF controls, question-bank imports, and backups. Frontend JavaScript syntax can be checked with `node --check frontend/app.js`.

## Source structure

```text
securepaper/
  backend/main.py           Version 3 FastAPI routes, auth, SQLite services
  backend/schema.sql        Original normalized question/session tables
  backend/schema_v3.sql     Additive student, teacher and exam schema
  backend/selector.py       Existing rules-based question selection
  frontend/index.html       SPA entry point
  frontend/app.js           Student and teacher portal interactions
  frontend/styles.css       New responsive Version 3 design
  frontend/favicon.svg
  data/securepaper.db       Example bank snapshot (not the current Render DB)
  seed/seed_questions.json  Original tagged MCQ seed source
  scripts/backup_db.py      Safe live database backup command
  scripts/reset_teacher_password.py
  samples/roll_assignments.csv
  tests/test_v3.py
  legacy/version2/          Previous frontend/backend kept for reference
  Dockerfile, compose.yaml, render.yaml, start.sh, .env.example
  README.md, RENDER_UPDATE_GUIDE.md, CLAUDE_HANDOFF.md
```
