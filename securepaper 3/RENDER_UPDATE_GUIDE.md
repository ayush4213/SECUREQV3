# Updating the existing SecurePaper Render website to Version 3

**Current service URL:** https://secure-ques-q.onrender.com/

These are deployment instructions, not evidence that the live service has already been updated.

## 1. Protect the live database first

Locate your existing Render service's `SECUREPAPER_DATA_DIR` environment variable and disk mount. The previous SecurePaper app used SQLite at `<SECUREPAPER_DATA_DIR>/securepaper.db`. The downloadable source also includes an older bank snapshot, but **that is not guaranteed to contain questions or sessions added later on the live website**.

Preserve the original disk and back up the active SQLite database. On a machine/shell that can access the volume, from the project root:

```bash
python -m scripts.backup_db /path/to/a/safe/backup-before-v3.db
```

Do **not** delete the disk or deploy with a new blank disk path if you need existing data. If the current Render plan uses ephemeral filesystem storage without a persistent disk, obtain a backup first; redeploying may otherwise reset data. Consider using a persistent disk or managed database for real usage.

## 2. Replace source code on the existing deployment branch

Unzip the release and use the files inside `securepaper/` as the new source. Commit/push them to the repository and branch that the existing Render web service deploys. Keep the existing service settings, domain, persistent disk and environment variables. The supplied `render.yaml` is an optional reference for a *new* service; **do not accidentally create a second Render service when updating the existing one**.

## 3. Set initial teacher credentials

For the first boot with Version 3, provide:

```
SECUREPAPER_TEACHER_EMAIL=teacher@securepaper.local
SECUREPAPER_TEACHER_PASSWORD=<a long unique password you choose>
```

You may use your school's preferred teacher email. If `SECUREPAPER_TEACHER_PASSWORD` is not set but the previous service already has `SECUREPAPER_ADMIN_KEY`, the app accepts that existing secret as the first teacher's password. **Do not rely on the old v2 example default admin key.**

Bootstrap happens only while there are no teacher records. Changing an environment variable later does not silently change existing users' passwords. Use the website's Account settings or the documented operator reset script.

Keep the existing `SECUREPAPER_DATA_DIR` exactly as it is configured on your current live service. If setting up a new persistent disk instead, `/var/data` is an example, not a mandatory path.

## 4. Build and start

Docker service: use `Dockerfile`, which installs `requirements.txt` (including the Excel exporter), copies application files, and runs `./start.sh`. The application listens on `$PORT` with one Uvicorn worker.

Or use the Python runtime:

```
pip install -r requirements.txt
./start.sh
```

At startup, `backend/schema.sql` and `backend/schema_v3.sql` create missing tables with `IF NOT EXISTS`. Existing `questions`, `question_options` and historical exam sessions are **not dropped or reseeded** if questions already exist.

## 5. Verify after deployment

1. Open `/api/health`. Confirm `status: ok`, `version: 3`, and `teacher_configured: true`.
2. Open the website and choose **Teacher Login**. Sign in with the configured teacher email and initial password.
3. Open Question bank and confirm your existing questions and option markers are present.
4. Create two students with distinct roll numbers, then create one examination with two paper sets and assign one to each student.
5. Sign in as each student and confirm only that student's assigned paper is listed and that future papers are locked.
6. Create a self-practice test, answer questions, submit and view the stored score.
7. After the scheduled start, verify that the assigned paper opens, its timer counts down, and its result appears in the teacher dashboard.
8. Export the exam results in CSV and Excel formats.

## 6. Recommended Render settings

- HTTPS enabled via Render's standard domain or custom domain.
- One Uvicorn worker (SQLite-based architecture).
- Persistent disk mounted to the same database directory as the previous deployment.
- Unique private teacher credential in Render environment settings.
- Regular off-service SQLite backups.

## Rollback

If the upgrade must be rolled back, redeploy the earlier source *without deleting the new database or disk*. SQLite additions do not remove v2 tables; however, old v2 source does not understand the new v3 authentication, exam and result tables. Retain a full pre-upgrade database backup for a clean rollback. Do not overwrite new student results with an older bank snapshot.
