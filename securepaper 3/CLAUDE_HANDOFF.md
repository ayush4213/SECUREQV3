# SecurePaper V3 — integration and hosting handoff

**Target existing site:** https://secure-ques-q.onrender.com/

## What changed from the provided source

- Original `questions` and `question_options` data model, seeded bank and `backend/selector.py` retained.
- New normalized additive schema `backend/schema_v3.sql` for users, secure sessions, teacher exams, distinct paper sets, roll assignments, student attempts and results.
- `backend/main.py` replaced with role-checked V3 endpoints. Insecure anonymous v2 session endpoints and shared-key admin endpoints are no longer exposed; earlier source is under `legacy/version2/`.
- `frontend/` replaced with a newly designed landing page and responsive student/teacher portal; no build system or CDN dependency.
- Teacher forms: student management, exam creation (automatic/manual paper sets), assignment CSV import, question-bank maintenance, exams list, result analytics, per-student detail, Excel/CSV export.
- Student forms: login, practice creation (automatic/manual questions), assigned tests, locked scheduled paper, answer selection/navigator, countdown, submission and result review.
- Lock animation appears only on the student's not-yet-open exam screen. Create-test success text is exactly `Test successfully saved.`

## Deployment prerequisites

- Preserve live Render disk and `SECUREPAPER_DATA_DIR` when swapping source. Existing live database was **not** retrieved remotely and may differ from the included snapshot.
- If no teacher exists, bootstrap teacher email+password from `SECUREPAPER_TEACHER_EMAIL` and `SECUREPAPER_TEACHER_PASSWORD`; previous `SECUREPAPER_ADMIN_KEY` is supported only as a first-time bootstrap fallback.
- Python 3.10+; dependencies `fastapi`, `uvicorn`, `pydantic`, `openpyxl`.
- Keep one Uvicorn worker with SQLite; do not add multiple workers without redesigning the storage and scheduling architecture.

## Exact schedule behavior

The exam is locked before the teacher's scheduled start. The fixed end is `scheduled start + duration`; students who join late receive only the remaining duration. The backend refuses attempts before the start or after the end. Once started, options are materialized per student. Active attempts are finalized by a periodic task and by any subsequent API interaction if the deadline has passed.

Student practice results show answer reviews at submission; teacher exam results show marks on submission and correct-answer review after the scheduled window ends. Teachers with ownership can always view detailed exam results. Student practice/question-picker inventory filters out items reserved for unfinished teacher exams.

## Validation results

- Run `python -m pytest -q tests/test_v3.py` (13 integration tests at the time of release).
- Run `node --check frontend/app.js` for the frontend script.
- A lightweight JavaScript runtime flow was checked for both role logins, student creation, exam builder, locked paper and practice start.
- A full Chromium visual test could not be completed in the authoring environment because browser navigation was administratively blocked. Perform the visual responsive QA after deploying to a staging environment.

## Deployment checklist

See `RENDER_UPDATE_GUIDE.md`. For a quick local verification:

```bash
export SECUREPAPER_TEACHER_EMAIL=teacher@securepaper.local
export SECUREPAPER_TEACHER_PASSWORD='a-long-unique-secret'
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

One student account cannot access another student’s assignment or result endpoints, and teacher results are scoped to the owning teacher. Passwords are salted PBKDF2 hashes, sessions use random cookie tokens persisted only as SHA-256 hashes, and API mutations require a per-session CSRF header.
