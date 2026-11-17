"""SecurePaper Version 3: role-isolated teacher/student examination portal.

Uses the existing normalized MCQ tables without resetting them. All question-paper
access, scheduling, submissions and results are authorized and verified server-side.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
import uuid
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from . import selector

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get('SECUREPAPER_DATA_DIR', str(ROOT / 'data'))).resolve()
DB_PATH = DATA_DIR / 'securepaper.db'
SEED_PATH = ROOT / 'seed' / 'seed_questions.json'
UTC = timezone.utc
COOKIE_NAME = 'sp_v3_session'
TOKEN_HOURS = 24
PASSWORD_ITERATIONS = 360_000
LOGIN_FAILURES: dict[str, deque[float]] = defaultdict(deque)


def now() -> datetime:
    return datetime.now(UTC)


def stamp(value: datetime | None = None) -> str:
    return (value or now()).astimezone(UTC).isoformat()


def parsed(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def uid() -> str:
    return uuid.uuid4().hex


@contextmanager
def database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=25, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 25000')
    try:
        yield conn
    finally:
        conn.close()


def normalize_options(correct: str, wrong: list[str]):
    correct = correct.strip()
    wrong = [value.strip() for value in wrong]
    if not correct or len(wrong) < 3 or len(wrong) > 30 or any(not v for v in wrong):
        raise ValueError('A question needs one correct option and 3–30 wrong options.')
    if len(set(v.casefold() for v in [correct, *wrong])) != len(wrong) + 1:
        raise ValueError('Answer options must be different.')
    return correct, wrong


def insert_question(c: sqlite3.Connection, question: dict) -> str:
    correct, wrong = normalize_options(question['correct_option'], question['wrong_options'])
    subject, topic, text = [str(question[x]).strip() for x in ('subject', 'topic', 'text')]
    if not all((subject, topic, text)):
        raise ValueError('Subject, topic and question are required.')
    if question['difficulty'] not in selector.DIFFICULTIES:
        raise ValueError('Difficulty must be easy, medium or hard.')
    if question['question_type'] not in ('conceptual', 'numerical', 'application', 'reasoning'):
        raise ValueError('Invalid question type.')
    if c.execute('SELECT 1 FROM questions WHERE subject=? AND lower(trim(text))=lower(?)', (subject, text)).fetchone():
        raise ValueError('A question with this text already exists for the subject.')
    question_id = uid()
    c.execute('INSERT INTO questions(id,subject,topic,difficulty,question_type,text,created_at) VALUES(?,?,?,?,?,?,?)',
              (question_id, subject, topic, question['difficulty'], question['question_type'], text, stamp()))
    for option_text, correct_flag in [(correct, 1), *[(v, 0) for v in wrong]]:
        c.execute('INSERT INTO question_options(id,question_id,text,is_correct) VALUES(?,?,?,?)',
                  (uid(), question_id, option_text, correct_flag))
    return question_id


def hash_password(password: str) -> str:
    if len(password) < 8 or len(password) > 128:
        raise ValueError('Password must contain 8–128 characters.')
    salt = secrets.token_bytes(16)
    result = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return f'pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${result.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt, expected = encoded.split('$')
        if algo != 'pbkdf2_sha256' or int(iterations) > 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def public_user(r: sqlite3.Row | dict) -> dict:
    return {key: r[key] for key in ('id', 'role', 'name', 'roll_number', 'email', 'active')}


def init_db():
    with database() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript((ROOT / 'backend' / 'schema.sql').read_text(encoding='utf8'))
        c.executescript((ROOT / 'backend' / 'schema_v3.sql').read_text(encoding='utf8'))
        if not c.execute('SELECT 1 FROM questions LIMIT 1').fetchone():
            questions = json.loads(SEED_PATH.read_text(encoding='utf8'))
            c.execute('BEGIN IMMEDIATE')
            try:
                for question in questions:
                    insert_question(c, question)
                c.commit()
            except Exception:
                c.rollback()
                raise
        if not c.execute("SELECT 1 FROM users WHERE role='teacher' LIMIT 1").fetchone():
            bootstrap_password = os.environ.get('SECUREPAPER_TEACHER_PASSWORD') or os.environ.get('SECUREPAPER_ADMIN_KEY')
            if bootstrap_password:
                bootstrap_email = os.environ.get('SECUREPAPER_TEACHER_EMAIL', 'teacher@securepaper.local').strip().lower()
                c.execute('INSERT INTO users(id,role,name,email,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                          (uid(), 'teacher', 'Lead Teacher', bootstrap_email, hash_password(bootstrap_password), stamp(), stamp()))
        c.execute('DELETE FROM auth_sessions WHERE expires_at < ?', (stamp(),))


def finalize_attempt(c, attempt_id: str) -> None:
    attempt = c.execute('SELECT * FROM v3_attempts WHERE id=?', (attempt_id,)).fetchone()
    if not attempt:
        raise HTTPException(404, 'Attempt not found.')
    if attempt['status'] == 'submitted':
        return
    correct = c.execute('''SELECT COUNT(*) FROM v3_attempt_answers ans
            JOIN question_options opt ON opt.id=ans.option_id
            WHERE ans.attempt_id=? AND opt.is_correct=1''', (attempt_id,)).fetchone()[0]
    answered = c.execute('SELECT COUNT(*) FROM v3_attempt_answers WHERE attempt_id=?', (attempt_id,)).fetchone()[0]
    wrong = answered - correct
    score = round(correct * attempt['marks_per_question'] - wrong * attempt['negative_marks'], 3)
    c.execute('''UPDATE v3_attempts SET status='submitted', submitted_at=?, score=?, correct_count=?
                 WHERE id=? AND status='active' ''', (stamp(), score, correct, attempt_id))


def sweep_expired(c) -> int:
    ids = [r[0] for r in c.execute("SELECT id FROM v3_attempts WHERE status='active' AND deadline_at<=?", (stamp(),))]
    for attempt_id in ids:
        finalize_attempt(c, attempt_id)
    return len(ids)


async def expiry_worker():
    while True:
        await asyncio.sleep(15)
        try:
            with database() as c:
                c.execute('BEGIN IMMEDIATE')
                sweep_expired(c)
                c.commit()
        except Exception:
            # A later request also reconciles expired attempts; no background job is authoritative.
            pass


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    worker = asyncio.create_task(expiry_worker())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title='SecurePaper Examination Management', version='3.0.0', lifespan=lifespan)
origins = [entry.strip() for entry in os.getenv('SECUREPAPER_CORS_ORIGINS', '').split(',') if entry.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=['GET','POST','PATCH','OPTIONS'],
                       allow_headers=['Content-Type','X-CSRF-Token'])


@app.middleware('http')
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'"
    )
    if request.url.scheme == 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def auth_context(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, 'Please sign in.')
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database() as c:
        record = c.execute('''SELECT u.*, s.csrf_token, s.expires_at FROM auth_sessions s
            JOIN users u ON u.id=s.user_id WHERE s.token_hash=?''', (token_hash,)).fetchone()
        if not record or not record['active'] or parsed(record['expires_at']) <= now():
            raise HTTPException(401, 'Session expired. Please sign in again.')
        return {'user': public_user(record), 'csrf': record['csrf_token'], 'token_hash': token_hash}


def teacher(context=Depends(auth_context)):
    if context['user']['role'] != 'teacher':
        raise HTTPException(403, 'Teacher access required.')
    return context


def student(context=Depends(auth_context)):
    if context['user']['role'] != 'student':
        raise HTTPException(403, 'Student access required.')
    return context


def csrf_check(request: Request, context=Depends(auth_context)):
    value = request.headers.get('X-CSRF-Token', '')
    if not value or not secrets.compare_digest(value, context['csrf']):
        raise HTTPException(403, 'Invalid request token.')
    return context


def teacher_write(context=Depends(csrf_check)):
    if context['user']['role'] != 'teacher':
        raise HTTPException(403, 'Teacher access required.')
    return context


def student_write(context=Depends(csrf_check)):
    if context['user']['role'] != 'student':
        raise HTTPException(403, 'Student access required.')
    return context


class Login(BaseModel):
    role: Literal['teacher', 'student']
    identifier: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=128)


class ChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class StudentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    roll_number: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=8, max_length=128)


class StudentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    roll_number: str | None = Field(default=None, min_length=1, max_length=40)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    active: bool | None = None


class QuestionCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=60)
    topic: str = Field(min_length=1, max_length=80)
    difficulty: Literal['easy', 'medium', 'hard']
    question_type: Literal['conceptual', 'numerical', 'application', 'reasoning']
    text: str = Field(min_length=6, max_length=1000)
    correct_option: str = Field(min_length=1, max_length=300)
    wrong_options: list[str] = Field(min_length=3, max_length=30)

    @field_validator('wrong_options')
    @classmethod
    def validate_wrong(cls, values):
        if any(not str(value).strip() or len(value) > 300 for value in values):
            raise ValueError('Every wrong option must contain 1–300 characters.')
        return values


class PracticeCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=60)
    topic: str = Field(default='', max_length=80)
    question_count: int = Field(default=10, ge=1, le=40)
    duration_minutes: int = Field(default=20, ge=1, le=180)
    question_ids: list[str] = Field(default_factory=list, max_length=40)


class AnswerSave(BaseModel):
    question_id: str
    option_id: str


class ManualSet(BaseModel):
    label: str = Field(min_length=1, max_length=2)
    question_ids: list[str] = Field(min_length=1, max_length=40)


class AssignmentInput(BaseModel):
    roll_number: str = Field(min_length=1, max_length=40)
    set_label: str | None = Field(default=None, max_length=2)


class ExamCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    subject: str = Field(min_length=1, max_length=60)
    topic: str = Field(default='', max_length=80)
    question_count: int = Field(ge=1, le=40)
    duration_minutes: int = Field(ge=1, le=180)
    marks_per_question: float = Field(default=1, gt=0, le=100)
    negative_marks: float = Field(default=0, ge=0, le=100)
    scheduled_at: datetime
    set_count: int = Field(default=1, ge=1, le=6)
    selection_mode: Literal['automatic', 'manual'] = 'automatic'
    question_pool_ids: list[str] = Field(default_factory=list, max_length=500)
    sets: list[ManualSet] = Field(default_factory=list, max_length=6)
    assignments: list[AssignmentInput] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def consistent(self):
        if self.negative_marks > self.marks_per_question:
            raise ValueError('Negative marking cannot exceed marks per question.')
        if self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None:
            raise ValueError('Scheduled time must include a timezone.')
        if self.selection_mode == 'manual' and len(self.sets) != self.set_count:
            raise ValueError('Provide one manual question list for every paper set.')
        return self


class AssignmentBatch(BaseModel):
    assignments: list[AssignmentInput] = Field(min_length=1, max_length=500)


@app.get('/api/health')
def health():
    with database() as c:
        has_teacher = bool(c.execute("SELECT 1 FROM users WHERE role='teacher' LIMIT 1").fetchone())
    return {'status': 'ok', 'version': '3', 'teacher_configured': has_teacher}


@app.post('/api/v3/auth/login')
def login(payload: Login, request: Request, response: Response):
    # Cookies are same-site. Reject explicit cross-origin browser login submissions.
    origin = request.headers.get('origin')
    if origin and urlsplit(origin).netloc.casefold() != request.headers.get('host','').casefold():
        raise HTTPException(403, 'Cross-origin login is not allowed.')
    key = f"{request.client.host if request.client else '?'}:{payload.role}:{payload.identifier.casefold()}"
    tick = time.monotonic()
    strikes = LOGIN_FAILURES[key]
    while strikes and tick - strikes[0] > 900:
        strikes.popleft()
    if len(strikes) >= 12:
        raise HTTPException(429, 'Too many login attempts. Try again later.')
    identifier = payload.identifier.strip()
    column = 'email' if payload.role == 'teacher' else 'roll_number'
    with database() as c:
        person = c.execute(f'SELECT * FROM users WHERE role=? AND {column}=?', (payload.role, identifier)).fetchone()
        if not person or not person['active'] or not verify_password(payload.password, person['password_hash']):
            strikes.append(tick)
            raise HTTPException(401, 'Invalid credentials.')
        LOGIN_FAILURES.pop(key, None)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(28)
        c.execute('INSERT INTO auth_sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES(?,?,?,?,?)',
                  (hashlib.sha256(token.encode()).hexdigest(), person['id'], csrf, stamp(), stamp(now() + timedelta(hours=TOKEN_HOURS))))
    response.set_cookie(COOKIE_NAME, token, max_age=TOKEN_HOURS * 3600,
                        secure=(request.url.scheme == 'https' or request.headers.get('x-forwarded-proto','').lower() == 'https'),
                        httponly=True, samesite='lax', path='/')
    return {'user': public_user(person), 'csrf_token': csrf}


@app.get('/api/v3/auth/me')
def whoami(context=Depends(auth_context)):
    return {'user': context['user'], 'csrf_token': context['csrf']}


@app.post('/api/v3/auth/logout')
def logout(response: Response, context=Depends(csrf_check)):
    with database() as c:
        c.execute('DELETE FROM auth_sessions WHERE token_hash=?', (context['token_hash'],))
    response.delete_cookie(COOKIE_NAME, path='/')
    return {'ok': True}


@app.post('/api/v3/auth/password')
def change_password(payload: ChangePassword, context=Depends(csrf_check)):
    with database() as c:
        user = c.execute('SELECT password_hash FROM users WHERE id=?', (context['user']['id'],)).fetchone()
        if not user or not verify_password(payload.old_password, user['password_hash']):
            raise HTTPException(403, 'Current password does not match.')
        c.execute('UPDATE users SET password_hash=?,updated_at=? WHERE id=?',
                  (hash_password(payload.new_password), stamp(), context['user']['id']))
        c.execute('DELETE FROM auth_sessions WHERE user_id=? AND token_hash<>?',
                  (context['user']['id'], context['token_hash']))
    return {'ok': True}


@app.get('/api/v3/catalog')
def catalog(context=Depends(auth_context)):
    with database() as c:
        rows = c.execute('''SELECT subject,topic,difficulty,question_type,COUNT(*) AS count FROM questions
             WHERE active=1 GROUP BY subject,topic,difficulty,question_type ORDER BY subject,topic''')
        all_rows = [dict(row) for row in rows]
    subjects: dict[str, dict] = {}
    for row in all_rows:
        subject = subjects.setdefault(row['subject'], {'name': row['subject'], 'count': 0, 'topics': {}})
        subject['count'] += row['count']
        subject['topics'][row['topic']] = subject['topics'].get(row['topic'], 0) + row['count']
    return {'subjects': [{'name': s['name'], 'count': s['count'],
                          'topics': [{'name': name, 'count': count} for name,count in sorted(s['topics'].items())]}
                         for s in subjects.values()], 'total_questions': sum(s['count'] for s in subjects.values()),
            'server_now': stamp()}


def reserved_questions(c) -> set[str]:
    """Question IDs in teacher-set exams that have not finished yet.

    Student practice and question picking must not disclose upcoming paper items.
    Teacher-managed item bank remains fully available to its authorized owners.
    """
    reserved = set()
    current = now()
    for row in c.execute('''SELECT sq.question_id, ex.scheduled_at, ex.duration_minutes
             FROM v3_set_questions sq JOIN v3_paper_sets ps ON ps.id=sq.set_id
             JOIN v3_exams ex ON ex.id=ps.exam_id'''):
        if current < parsed(row['scheduled_at']) + timedelta(minutes=row['duration_minutes']):
            reserved.add(row['question_id'])
    return reserved


def practice_bank(c, subject: str, topic: str = '') -> list[dict]:
    excluded = reserved_questions(c)
    return [q for q in eligible_bank(c, subject, topic) if q['id'] not in excluded]


def eligible_bank(c, subject: str, topic: str = '', question_ids: list[str] | None = None) -> list[dict]:
    sql = '''SELECT q.id,q.subject,q.topic,q.difficulty,q.question_type,q.text FROM questions q
          WHERE q.active=1 AND q.subject=? AND (?='' OR q.topic=?)
          AND (SELECT COUNT(*) FROM question_options o WHERE o.question_id=q.id AND o.is_correct=1)=1
          AND (SELECT COUNT(*) FROM question_options o WHERE o.question_id=q.id AND o.is_correct=0)>=3'''
    pool = [dict(r) for r in c.execute(sql, (subject, topic, topic))]
    if question_ids:
        wanted = set(question_ids)
        if len(wanted) != len(question_ids):
            raise HTTPException(422, 'Duplicate question IDs are not allowed.')
        chosen = [q for q in pool if q['id'] in wanted]
        if len(chosen) != len(wanted):
            raise HTTPException(422, 'Some selected questions do not match the subject or topic.')
        return chosen
    return pool


@app.get('/api/v3/questions')
def question_picker(subject: str = '', topic: str = '', search: str = '', limit: int = Query(400, ge=1, le=500),
                    context=Depends(auth_context)):
    where, params = ['q.active=1'], []
    if subject:
        where.append('q.subject=?'); params.append(subject)
    if topic:
        where.append('q.topic=?'); params.append(topic)
    if search:
        where.append('(q.text LIKE ? OR q.topic LIKE ?)'); params.extend([f'%{search}%', f'%{search}%'])
    with database() as c:
        rows = c.execute('SELECT q.id,q.subject,q.topic,q.difficulty,q.question_type,q.text FROM questions q WHERE '
                         + ' AND '.join(where) + ' ORDER BY q.subject,q.topic,q.difficulty LIMIT ?', [*params, limit])
        results = [dict(r) for r in rows]
        if context['user']['role'] == 'student':
            excluded = reserved_questions(c)
            results = [q for q in results if q['id'] not in excluded]
        return results


def build_attempt(c, *, student_id: str, kind: str, title: str, subject: str, topic: str,
                  chosen: list[dict], duration_minutes: int, marks: float = 1, negative: float = 0,
                  assignment_id: str | None = None, deadline: datetime | None = None) -> str:
    attempt_id = secrets.token_urlsafe(22)
    current = now()
    until = deadline or current + timedelta(minutes=duration_minutes)
    c.execute('''INSERT INTO v3_attempts(id,student_id,kind,assignment_id,title,subject,topic,marks_per_question,
            negative_marks,started_at,deadline_at,total_questions) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
              (attempt_id, student_id, kind, assignment_id, title, subject, topic,
               marks, negative, stamp(current), stamp(until), len(chosen)))
    rng = secrets.SystemRandom()
    for position, question in enumerate(chosen):
        qid = question['id']
        c.execute('INSERT INTO v3_attempt_items(attempt_id,question_id,position) VALUES(?,?,?)',
                  (attempt_id, qid, position))
        options = [dict(r) for r in c.execute('SELECT id,is_correct FROM question_options WHERE question_id=?', (qid,))]
        right = [o for o in options if o['is_correct'] == 1]
        wrong = [o for o in options if o['is_correct'] == 0]
        if len(right) != 1 or len(wrong) < 3:
            raise HTTPException(422, 'A selected question has invalid answer options.')
        chosen_options = right + rng.sample(wrong, 3)
        rng.shuffle(chosen_options)
        for order, option in enumerate(chosen_options):
            c.execute('INSERT INTO v3_attempt_options(attempt_id,question_id,option_id,position) VALUES(?,?,?,?)',
                      (attempt_id, qid, option['id'], order))
    return attempt_id


def attempt_for_student(c, aid: str, student_id: str):
    record = c.execute('SELECT * FROM v3_attempts WHERE id=? AND student_id=?', (aid, student_id)).fetchone()
    if not record:
        raise HTTPException(404, 'Test not found.')
    return record


def attempt_review(c, aid: str) -> list[dict]:
    rows = c.execute('''SELECT q.id AS question_id,q.text,q.subject,ai.position,
             correct.text AS correct_text, correct.id AS correct_id,
             selected.text AS selected_text, selected.id AS selected_id
        FROM v3_attempt_items ai JOIN questions q ON q.id=ai.question_id
        JOIN question_options correct ON correct.question_id=q.id AND correct.is_correct=1
        LEFT JOIN v3_attempt_answers aa ON aa.attempt_id=ai.attempt_id AND aa.question_id=q.id
        LEFT JOIN question_options selected ON selected.id=aa.option_id
        WHERE ai.attempt_id=? ORDER BY ai.position''', (aid,))
    return [{'question_id': r['question_id'], 'text': r['text'], 'subject': r['subject'],
             'selected_text': r['selected_text'], 'correct_text': r['correct_text'],
             'is_correct': r['selected_id'] == r['correct_id']} for r in rows]


def review_released(c, attempt) -> bool:
    if attempt['kind'] == 'practice':
        return True
    scheduled = c.execute('''SELECT ex.scheduled_at,ex.duration_minutes FROM v3_assignments a
          JOIN v3_exams ex ON ex.id=a.exam_id WHERE a.id=?''', (attempt['assignment_id'],)).fetchone()
    return bool(scheduled and now() >= parsed(scheduled['scheduled_at']) + timedelta(minutes=scheduled['duration_minutes']))


def attempt_view(c, attempt_id: str, student_id: str, *, include_review: bool = True) -> dict:
    attempt = attempt_for_student(c, attempt_id, student_id)
    if attempt['status'] == 'active' and parsed(attempt['deadline_at']) <= now():
        c.execute('BEGIN IMMEDIATE')
        try:
            finalize_attempt(c, attempt_id)
            c.commit()
        except Exception:
            c.rollback()
            raise
        attempt = attempt_for_student(c, attempt_id, student_id)
    data = {key: attempt[key] for key in ('id','kind','assignment_id','title','subject','topic','marks_per_question',
            'negative_marks','started_at','deadline_at','submitted_at','status','score','correct_count','total_questions')}
    data['server_now'] = stamp()
    # These items exist only after a scheduled exam has started and passed access checks.
    if attempt['status'] == 'active':
        questions = c.execute('''SELECT q.id,q.subject,q.topic,q.difficulty,q.question_type,q.text,ai.position,
             aa.option_id AS selected_option FROM v3_attempt_items ai
             JOIN questions q ON q.id=ai.question_id
             LEFT JOIN v3_attempt_answers aa ON aa.attempt_id=ai.attempt_id AND aa.question_id=q.id
             WHERE ai.attempt_id=? ORDER BY ai.position''', (attempt_id,))
        data['questions'] = []
        for q in questions:
            opts = c.execute('''SELECT qo.id,qo.text FROM v3_attempt_options ao
                 JOIN question_options qo ON qo.id=ao.option_id
                 WHERE ao.attempt_id=? AND ao.question_id=? ORDER BY ao.position''', (attempt_id, q['id']))
            data['questions'].append({key: q[key] for key in ('id','subject','topic','difficulty','question_type','text','position','selected_option')} |
                                     {'options': [dict(o) for o in opts]})
    elif include_review and review_released(c, attempt):
        data['review'] = attempt_review(c, attempt_id)
    else:
        data['review_available'] = False
    return data


@app.post('/api/v3/student/practice', status_code=201)
def create_practice(payload: PracticeCreate, context=Depends(student_write)):
    student_id = context['user']['id']
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            pool = practice_bank(c, payload.subject, payload.topic)
            if payload.question_ids:
                if len(payload.question_ids) != payload.question_count:
                    raise HTTPException(422, 'Select exactly the requested number of questions.')
                lookup = {q['id']: q for q in pool}
                if len(set(payload.question_ids)) != len(payload.question_ids) or any(x not in lookup for x in payload.question_ids):
                    raise HTTPException(422, 'Some selected questions are unavailable.')
                chosen = [lookup[qid] for qid in payload.question_ids]
            else:
                if len(pool) < payload.question_count:
                    raise HTTPException(422, 'Not enough questions for the selected subject and topic.')
                plan = selector.blueprint(pool, 'practice', [payload.subject], payload.question_count)
                seen = {r[0] for r in c.execute('''SELECT ai.question_id FROM v3_attempt_items ai
                            JOIN v3_attempts a ON a.id=ai.attempt_id WHERE a.student_id=?''', (student_id,))}
                chosen = selector.select_questions(pool, plan, seen, Counter(), set())
            attempt_id = build_attempt(c, student_id=student_id, kind='practice',
                      title=f'{payload.subject} Practice', subject=payload.subject, topic=payload.topic,
                      chosen=chosen, duration_minutes=payload.duration_minutes)
            c.commit()
        except Exception:
            c.rollback()
            raise
    return {'message': 'Test successfully saved.', 'attempt_id': attempt_id}


def exam_status(start: datetime, duration: int, attempt_status: str | None) -> str:
    if attempt_status == 'submitted':
        return 'Completed'
    if now() < start:
        return 'Upcoming'
    if now() >= start + timedelta(minutes=duration):
        return 'Completed'
    return 'Available'


def student_assignments(c, student_id: str):
    records = c.execute('''SELECT a.id AS assignment_id, ex.id AS exam_id, ex.name,ex.subject,ex.topic,
                 ex.question_count,ex.duration_minutes,ex.marks_per_question,ex.negative_marks,
                 ex.scheduled_at,s.label AS paper_set,att.id AS attempt_id,att.status AS attempt_status,att.score
          FROM v3_assignments a JOIN v3_exams ex ON ex.id=a.exam_id
          JOIN v3_paper_sets s ON s.id=a.set_id
          LEFT JOIN v3_attempts att ON att.assignment_id=a.id
          WHERE a.student_id=? ORDER BY ex.scheduled_at DESC''', (student_id,))
    results = []
    for r in records:
        entry = dict(r)
        entry['status'] = exam_status(parsed(r['scheduled_at']), r['duration_minutes'], r['attempt_status'])
        results.append(entry)
    return results


@app.get('/api/v3/student/dashboard')
def student_dashboard(context=Depends(student)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE'); sweep_expired(c); c.commit()
        assignments = student_assignments(c, context['user']['id'])
        attempts = [dict(r) for r in c.execute('''SELECT id,kind,title,subject,topic,started_at,deadline_at,
                     submitted_at,status,score,total_questions,marks_per_question FROM v3_attempts
                  WHERE student_id=? ORDER BY started_at DESC LIMIT 75''', (context['user']['id'],))]
    return {'assignments': assignments, 'attempts': attempts, 'server_now': stamp()}


@app.get('/api/v3/student/assignments/{assignment_id}')
def student_assignment_detail(assignment_id: str, context=Depends(student)):
    with database() as c:
        rows = student_assignments(c, context['user']['id'])
    entry = next((r for r in rows if r['assignment_id'] == assignment_id), None)
    if not entry:
        raise HTTPException(404, 'Assigned examination not found.')
    return {'assignment': entry, 'server_now': stamp()}


@app.post('/api/v3/student/assignments/{assignment_id}/start')
def start_assigned(assignment_id: str, context=Depends(student_write)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            a = c.execute('''SELECT a.id,a.set_id,ex.name,ex.subject,ex.topic,ex.scheduled_at,
                    ex.duration_minutes,ex.marks_per_question,ex.negative_marks
                 FROM v3_assignments a JOIN v3_exams ex ON ex.id=a.exam_id
                 WHERE a.id=? AND a.student_id=?''', (assignment_id, context['user']['id'])).fetchone()
            if not a:
                raise HTTPException(404, 'Examination not assigned to your account.')
            existing = c.execute('SELECT id FROM v3_attempts WHERE assignment_id=?', (assignment_id,)).fetchone()
            start = parsed(a['scheduled_at'])
            finish = start + timedelta(minutes=a['duration_minutes'])
            if now() < start:
                raise HTTPException(423, 'Your examination has not started.')
            if existing:
                c.commit()
                return {'attempt_id': existing['id']}
            if now() >= finish:
                raise HTTPException(409, 'The examination window has ended.')
            questions = [dict(q) for q in c.execute('''SELECT q.id,q.subject,q.topic,q.difficulty,q.question_type,q.text
                  FROM v3_set_questions sq JOIN questions q ON q.id=sq.question_id
                  WHERE sq.set_id=? ORDER BY sq.position''', (a['set_id'],))]
            attempt_id = build_attempt(c, student_id=context['user']['id'], kind='exam',
                    assignment_id=assignment_id, title=a['name'], subject=a['subject'], topic=a['topic'],
                    chosen=questions, duration_minutes=a['duration_minutes'],
                    marks=a['marks_per_question'], negative=a['negative_marks'], deadline=finish)
            c.commit()
        except Exception:
            c.rollback()
            raise
    return {'attempt_id': attempt_id}


@app.get('/api/v3/student/attempts/{attempt_id}')
def get_attempt(attempt_id: str, context=Depends(student)):
    with database() as c:
        return attempt_view(c, attempt_id, context['user']['id'])


@app.post('/api/v3/student/attempts/{attempt_id}/answer')
def save_answer(attempt_id: str, payload: AnswerSave, context=Depends(student_write)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            attempt = attempt_for_student(c, attempt_id, context['user']['id'])
            if attempt['status'] != 'active' or parsed(attempt['deadline_at']) <= now():
                finalize_attempt(c, attempt_id)
                c.commit()
                raise HTTPException(409, 'This examination has ended.')
            eligible = c.execute('''SELECT 1 FROM v3_attempt_options WHERE attempt_id=? AND question_id=? AND option_id=?''',
                                 (attempt_id, payload.question_id, payload.option_id)).fetchone()
            if not eligible:
                raise HTTPException(422, 'That option is not part of your question paper.')
            c.execute('''INSERT INTO v3_attempt_answers(attempt_id,question_id,option_id,answered_at)
                  VALUES(?,?,?,?) ON CONFLICT(attempt_id,question_id) DO UPDATE SET
                  option_id=excluded.option_id, answered_at=excluded.answered_at''',
                      (attempt_id, payload.question_id, payload.option_id, stamp()))
            c.commit()
        except HTTPException:
            if c.in_transaction:
                c.rollback()
            raise
        except Exception:
            c.rollback()
            raise
    return {'saved': True}


@app.post('/api/v3/student/attempts/{attempt_id}/submit')
def submit_attempt(attempt_id: str, context=Depends(student_write)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            attempt_for_student(c, attempt_id, context['user']['id'])
            finalize_attempt(c, attempt_id)
            c.commit()
        except Exception:
            c.rollback()
            raise
        return attempt_view(c, attempt_id, context['user']['id'])


@app.get('/api/v3/student/results/{attempt_id}')
def student_result(attempt_id: str, context=Depends(student)):
    with database() as c:
        attempt = attempt_for_student(c, attempt_id, context['user']['id'])
        if attempt['status'] == 'active' and parsed(attempt['deadline_at']) <= now():
            c.execute('BEGIN IMMEDIATE'); finalize_attempt(c, attempt_id); c.commit()
            attempt = attempt_for_student(c, attempt_id, context['user']['id'])
        if attempt['status'] != 'submitted':
            raise HTTPException(409, 'Submit the examination to view the result.')
        return attempt_view(c, attempt_id, context['user']['id'])


@app.get('/api/v3/teacher/dashboard')
def teacher_dashboard(context=Depends(teacher)):
    teacher_id = context['user']['id']
    with database() as c:
        c.execute('BEGIN IMMEDIATE'); sweep_expired(c); c.commit()
        students = c.execute("SELECT COUNT(*) FROM users WHERE role='student' AND created_by=?", (teacher_id,)).fetchone()[0]
        exams = c.execute('SELECT COUNT(*) FROM v3_exams WHERE teacher_id=?', (teacher_id,)).fetchone()[0]
        questions = c.execute('SELECT COUNT(*) FROM questions WHERE active=1').fetchone()[0]
        assigned = c.execute('''SELECT COUNT(*) FROM v3_assignments a JOIN v3_exams ex ON ex.id=a.exam_id
                   WHERE ex.teacher_id=?''', (teacher_id,)).fetchone()[0]
    return {'students': students, 'exams': exams, 'questions': questions, 'assigned': assigned}


@app.get('/api/v3/teacher/students')
def list_students(search: str = '', context=Depends(teacher)):
    with database() as c:
        sql = '''SELECT id,name,roll_number,active,created_at FROM users WHERE role='student' AND created_by=?'''
        params = [context['user']['id']]
        if search:
            sql += ' AND (roll_number LIKE ? OR name LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])
        sql += ' ORDER BY roll_number LIMIT 1000'
        return [dict(row) for row in c.execute(sql, params)]


@app.post('/api/v3/teacher/students', status_code=201)
def add_student(payload: StudentCreate, context=Depends(teacher_write)):
    roll = payload.roll_number.strip().upper()
    name = payload.name.strip()
    if not roll or not name:
        raise HTTPException(422, 'Student name and roll number are required.')
    with database() as c:
        try:
            student_id = uid()
            c.execute('''INSERT INTO users(id,role,name,roll_number,password_hash,created_by,created_at,updated_at)
                    VALUES(?,'student',?,?,?,?,?,?)''',
                      (student_id, name, roll, hash_password(payload.password), context['user']['id'], stamp(), stamp()))
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, 'This roll number is already registered.') from e
    return {'id': student_id, 'roll_number': roll, 'created': True}


@app.patch('/api/v3/teacher/students/{student_id}')
def edit_student(student_id: str, payload: StudentUpdate, context=Depends(teacher_write)):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, 'No changes provided.')
    mapped = {}
    for key, value in changes.items():
        if key == 'name' and value is not None:
            mapped[key] = value.strip()
        elif key == 'roll_number' and value is not None:
            mapped[key] = value.strip().upper()
        elif key == 'password' and value is not None:
            mapped['password_hash'] = hash_password(value)
        elif key == 'active' and value is not None:
            mapped['active'] = int(value)
    if any(not v for key,v in mapped.items() if key in ('name','roll_number')):
        raise HTTPException(422, 'Name and roll number cannot be empty.')
    if not mapped:
        raise HTTPException(422, 'No valid changes provided.')
    mapped['updated_at'] = stamp()
    columns = ','.join(f'{key}=?' for key in mapped)
    with database() as c:
        try:
            c.execute('BEGIN IMMEDIATE')
            cur = c.execute(f"UPDATE users SET {columns} WHERE id=? AND role='student' AND created_by=?",
                            [*mapped.values(), student_id, context['user']['id']])
            if not cur.rowcount:
                raise HTTPException(404, 'Student not found.')
            if mapped.get('active') == 0 or 'password_hash' in mapped:
                c.execute('DELETE FROM auth_sessions WHERE user_id=?', (student_id,))
            c.commit()
        except sqlite3.IntegrityError as e:
            c.rollback()
            raise HTTPException(409, 'This roll number is already registered.') from e
        except Exception:
            c.rollback()
            raise
    return {'updated': True}


def require_owned_exam(c, exam_id: str, teacher_id: str):
    exam = c.execute('SELECT * FROM v3_exams WHERE id=? AND teacher_id=?', (exam_id, teacher_id)).fetchone()
    if not exam:
        raise HTTPException(404, 'Examination not found.')
    return exam


def select_sets(c, payload: ExamCreate) -> list[list[dict]]:
    bank = eligible_bank(c, payload.subject.strip(), payload.topic.strip(),
                         payload.question_pool_ids if payload.selection_mode == 'automatic' else None)
    by_id = {question['id']: question for question in bank}
    n, k = payload.question_count, payload.set_count
    if payload.selection_mode == 'manual':
        if len(payload.sets) != k:
            raise HTTPException(422, 'A question list is required for every paper set.')
        fingerprints = set()
        sets = []
        for manual in payload.sets:
            if len(manual.question_ids) != n or len(set(manual.question_ids)) != n:
                raise HTTPException(422, 'Each set must contain exactly the requested number of distinct questions.')
            if any(qid not in by_id for qid in manual.question_ids):
                raise HTTPException(422, 'A manually selected question is unavailable for this subject/topic.')
            fingerprint = frozenset(manual.question_ids)
            if fingerprint in fingerprints:
                raise HTTPException(422, 'Every paper set must contain a different question combination.')
            fingerprints.add(fingerprint)
            sets.append([by_id[qid] for qid in manual.question_ids])
        return sets
    if len(bank) < n + k - 1:
        raise HTTPException(422, f'This examination needs at least {n + k - 1} available questions to create {k} distinct sets.')
    rng = secrets.SystemRandom()
    candidates = bank[:]
    rng.shuffle(candidates)
    if len(bank) >= n*k:
        # Reuse the original constraint-aware selector to balance the approved
        # difficulty mix and question types, while keeping each paper disjoint.
        selected_sets = []
        used_questions = set()
        for _ in range(k):
            available = [q for q in candidates if q['id'] not in used_questions]
            plan = selector.blueprint(available, 'class_test', [payload.subject.strip()], n)
            chosen = selector.select_questions(available, plan, set(), Counter(), set(), rng)
            selected_sets.append(chosen)
            used_questions.update(q['id'] for q in chosen)
        return selected_sets
    sets, used = [], set()
    for index in range(k):
        # Rotating windows guarantee distinct combinations for len(bank) >= n+k-1.
        start = index
        chosen = candidates[start:start+n]
        signature = frozenset(q['id'] for q in chosen)
        if len(chosen) != n or signature in used:
            raise HTTPException(422, 'Unable to form distinct papers from the available question bank.')
        rng.shuffle(chosen)
        used.add(signature)
        sets.append(chosen)
    return sets


def validate_assignments(c, teacher_id: str, assignments: list[AssignmentInput], labels: list[str]) -> list[tuple[str,str,str]]:
    if len({a.roll_number.strip().upper() for a in assignments}) != len(assignments):
        raise HTTPException(422, 'Roll numbers must not be repeated.')
    resolved = []
    for index, assignment in enumerate(assignments):
        roll = assignment.roll_number.strip().upper()
        person = c.execute('''SELECT id FROM users WHERE role='student' AND created_by=?
                  AND roll_number=? AND active=1''', (teacher_id, roll)).fetchone()
        if not person:
            raise HTTPException(422, f'Roll number {roll} is not an active student in your account.')
        label = (assignment.set_label or labels[index % len(labels)]).strip().upper()
        if label not in labels:
            raise HTTPException(422, f'Invalid paper set {label} for roll number {roll}.')
        resolved.append((person['id'], roll, label))
    return resolved


@app.post('/api/v3/teacher/exams', status_code=201)
def create_exam(payload: ExamCreate, context=Depends(teacher_write)):
    scheduled = payload.scheduled_at.astimezone(UTC)
    if scheduled + timedelta(minutes=payload.duration_minutes) <= now():
        raise HTTPException(422, 'The examination end time must be in the future.')
    labels = list('ABCDEF')[:payload.set_count]
    if payload.selection_mode == 'manual' and [s.label.strip().upper() for s in payload.sets] != labels:
        raise HTTPException(422, 'Manual paper sets must be labelled A, B, C, and so on.')
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            grouped = select_sets(c, payload)
            assigned = validate_assignments(c, context['user']['id'], payload.assignments, labels)
            exam_id = uid()
            c.execute('''INSERT INTO v3_exams(id,teacher_id,name,subject,topic,question_count,
                duration_minutes,marks_per_question,negative_marks,scheduled_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                      (exam_id,context['user']['id'],payload.name.strip(),payload.subject.strip(),payload.topic.strip(),
                       payload.question_count,payload.duration_minutes,payload.marks_per_question,
                       payload.negative_marks,stamp(scheduled),stamp()))
            sets_by_label = {}
            for label, questions in zip(labels, grouped):
                set_id = uid()
                sets_by_label[label] = set_id
                c.execute('INSERT INTO v3_paper_sets(id,exam_id,label) VALUES(?,?,?)', (set_id, exam_id, label))
                for position, question in enumerate(questions):
                    c.execute('INSERT INTO v3_set_questions(set_id,question_id,position) VALUES(?,?,?)',
                              (set_id, question['id'], position))
            for student_id, _roll, label in assigned:
                c.execute('''INSERT INTO v3_assignments(id,exam_id,student_id,set_id,assigned_at)
                   VALUES(?,?,?,?,?)''', (uid(), exam_id, student_id, sets_by_label[label], stamp()))
            c.commit()
        except Exception:
            c.rollback()
            raise
    return {'message': 'Test successfully saved.', 'exam_id': exam_id}


@app.get('/api/v3/teacher/exams')
def teacher_exams(context=Depends(teacher)):
    with database() as c:
        results = c.execute('''SELECT e.*,COUNT(DISTINCT s.id) AS set_count,
                 COUNT(DISTINCT a.id) AS assigned_count,
                 COUNT(DISTINCT CASE WHEN att.status='submitted' THEN att.id END) AS submitted_count
            FROM v3_exams e LEFT JOIN v3_paper_sets s ON s.exam_id=e.id
            LEFT JOIN v3_assignments a ON a.exam_id=e.id
            LEFT JOIN v3_attempts att ON att.assignment_id=a.id
            WHERE e.teacher_id=? GROUP BY e.id ORDER BY e.scheduled_at DESC''', (context['user']['id'],))
        return [{**dict(r), 'status': exam_status(parsed(r['scheduled_at']), r['duration_minutes'], None)} for r in results]


@app.get('/api/v3/teacher/exams/{exam_id}')
def teacher_exam_detail(exam_id: str, context=Depends(teacher)):
    with database() as c:
        exam = dict(require_owned_exam(c, exam_id, context['user']['id']))
        sets = [dict(r) for r in c.execute('SELECT id,label FROM v3_paper_sets WHERE exam_id=? ORDER BY label', (exam_id,))]
        for paper_set in sets:
            paper_set['question_ids'] = [r[0] for r in c.execute('''SELECT question_id FROM v3_set_questions
                   WHERE set_id=? ORDER BY position''', (paper_set['id'],))]
        assignments = [dict(r) for r in c.execute('''SELECT a.id,u.name,u.roll_number,s.label AS paper_set
                 FROM v3_assignments a JOIN users u ON u.id=a.student_id
                 JOIN v3_paper_sets s ON s.id=a.set_id WHERE a.exam_id=? ORDER BY u.roll_number''', (exam_id,))]
    return {'exam':exam, 'sets':sets, 'assignments': assignments}


@app.post('/api/v3/teacher/exams/{exam_id}/assignments')
def add_assignments(exam_id: str, payload: AssignmentBatch, context=Depends(teacher_write)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            exam = require_owned_exam(c, exam_id, context['user']['id'])
            if now() >= parsed(exam['scheduled_at']):
                raise HTTPException(409, 'Assignments cannot be changed after the exam starts.')
            sets = {row['label']: row['id'] for row in c.execute('SELECT label,id FROM v3_paper_sets WHERE exam_id=?', (exam_id,))}
            resolved = validate_assignments(c, context['user']['id'], payload.assignments, sorted(sets))
            for student_id, _roll, label in resolved:
                c.execute('''INSERT INTO v3_assignments(id,exam_id,student_id,set_id,assigned_at)
                      VALUES(?,?,?,?,?) ON CONFLICT(exam_id,student_id)
                      DO UPDATE SET set_id=excluded.set_id,assigned_at=excluded.assigned_at''',
                          (uid(), exam_id, student_id, sets[label], stamp()))
            c.commit()
        except Exception:
            c.rollback()
            raise
    return {'updated': len(payload.assignments)}


def results_data(c, exam_id: str, teacher_id: str):
    exam = dict(require_owned_exam(c, exam_id, teacher_id))
    records = [dict(r) for r in c.execute('''SELECT u.id AS student_id,u.name,u.roll_number,
               ps.label AS paper_set,att.id AS attempt_id,att.status AS attempt_status,
               att.score,att.correct_count,att.submitted_at,att.started_at
        FROM v3_assignments a JOIN users u ON u.id=a.student_id
        JOIN v3_paper_sets ps ON ps.id=a.set_id
        LEFT JOIN v3_attempts att ON att.assignment_id=a.id
        WHERE a.exam_id=? ORDER BY u.roll_number''', (exam_id,))]
    ending = parsed(exam['scheduled_at']) + timedelta(minutes=exam['duration_minutes'])
    attempted = 0
    for r in records:
        if r['attempt_status'] == 'submitted':
            r['submission_status'] = 'Submitted'
        elif r['attempt_status'] == 'active':
            r['submission_status'] = 'In progress'
        elif now() >= ending:
            r['submission_status'] = 'Not attempted'
        else:
            r['submission_status'] = 'Not started'
        if r['attempt_id']:
            attempted += 1
        r['total_marks'] = round(exam['question_count'] * exam['marks_per_question'], 3)
        r['percentage'] = round(100 * r['score'] / r['total_marks'], 2) if r['score'] is not None and r['total_marks'] else None
    return {'exam':exam, 'rows':records, 'summary':{'total_assigned':len(records),
            'attempted':attempted, 'not_attempted':len(records)-attempted,
            'submitted':sum(r['submission_status']=='Submitted' for r in records)}}


@app.get('/api/v3/teacher/exams/{exam_id}/results')
def teacher_results(exam_id: str, context=Depends(teacher)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE'); sweep_expired(c); c.commit()
        return results_data(c, exam_id, context['user']['id'])


@app.get('/api/v3/teacher/exams/{exam_id}/results/{student_id}')
def teacher_student_result(exam_id: str, student_id: str, context=Depends(teacher)):
    with database() as c:
        require_owned_exam(c, exam_id, context['user']['id'])
        record = c.execute('''SELECT att.id,att.status,att.score,att.correct_count,att.total_questions,
                  att.marks_per_question,att.negative_marks,u.name,u.roll_number,ps.label AS paper_set
             FROM v3_assignments a JOIN users u ON u.id=a.student_id
             JOIN v3_paper_sets ps ON ps.id=a.set_id
             LEFT JOIN v3_attempts att ON att.assignment_id=a.id
             WHERE a.exam_id=? AND a.student_id=?''', (exam_id, student_id)).fetchone()
        if not record:
            raise HTTPException(404, 'Student assignment not found.')
        detail = dict(record)
        if record['id']:
            detail['review'] = attempt_review(c, record['id'])
        return detail


@app.get('/api/v3/teacher/exams/{exam_id}/export')
def export_results(exam_id: str, format: Literal['csv','xlsx'] = 'csv', context=Depends(teacher)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE'); sweep_expired(c); c.commit()
        report = results_data(c, exam_id, context['user']['id'])
    header = ['Roll number','Student name','Paper set','Marks obtained','Total marks','Percentage','Status','Submitted at']
    rows = [[r['roll_number'],r['name'],r['paper_set'],r['score'] if r['score'] is not None else '',
             r['total_marks'],r['percentage'] if r['percentage'] is not None else '',
             r['submission_status'],r['submitted_at'] or ''] for r in report['rows']]
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        # Neutralize Excel CSV formula injection from user-controlled names/roll numbers.
        for row in rows:
            writer.writerow(["'" + str(v) if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in row])
        content = ('\ufeff' + output.getvalue()).encode('utf-8')
        return Response(content=content, media_type='text/csv; charset=utf-8', headers={
            'Content-Disposition': f'attachment; filename="securepaper-results-{exam_id[:8]}.csv"'})
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = 'Examination Results'
    ws.append([report['exam']['name']])
    ws.append([f"Subject: {report['exam']['subject']}"])
    ws.append([])
    ws.append(header)
    for row in rows:
        # Interpret all imported student/roll content as spreadsheet text, never formulas.
        safe = [('\'' + v if isinstance(v, str) and v.lstrip().startswith(('=','+','-','@')) else v)
                for v in row]
        ws.append(safe)
    for cell in ws[4]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='27385F')
        cell.alignment = Alignment(horizontal='left')
    for col, width in {'A':19,'B':26,'C':16,'D':20,'E':17,'F':15,'G':20,'H':28}.items():
        ws.column_dimensions[col].width = width
    for cells in ws.iter_rows(min_row=5):
        for column in (1,2,3,7,8):
            cell = cells[column-1]
            cell.data_type = 's'
    output = io.BytesIO()
    wb.save(output)
    return Response(content=output.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="securepaper-results-{exam_id[:8]}.xlsx"'})


@app.get('/api/v3/teacher/questions')
def teacher_questions(subject: str = '', topic: str = '', search: str = '', active: str = 'all',
                      limit: int = Query(500, ge=1, le=1000), context=Depends(teacher)):
    where, params = ['1=1'], []
    if subject:
        where.append('subject=?');params.append(subject)
    if topic:
        where.append('topic=?');params.append(topic)
    if search:
        where.append('(text LIKE ? OR topic LIKE ?)');params.extend([f'%{search}%',f'%{search}%'])
    if active in ('0','1'):
        where.append('active=?');params.append(int(active))
    with database() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM questions WHERE '+' AND '.join(where)
                     +' ORDER BY subject,topic,difficulty LIMIT ?', [*params,limit])]
        for q in rows:
            q['options'] = [dict(o) for o in c.execute('''SELECT id,text,is_correct FROM question_options
                           WHERE question_id=? ORDER BY is_correct DESC,text''', (q['id'],))]
        return rows


@app.post('/api/v3/teacher/questions', status_code=201)
def teacher_add_question(payload: QuestionCreate, context=Depends(teacher_write)):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            qid = insert_question(c, payload.model_dump())
            c.commit()
        except ValueError as e:
            c.rollback()
            raise HTTPException(422, str(e)) from e
        except Exception:
            c.rollback()
            raise
    return {'id':qid, 'created':True}


@app.post('/api/v3/teacher/questions/import')
def teacher_import(payload: list[QuestionCreate], context=Depends(teacher_write)):
    if not 1 <= len(payload) <= 500:
        raise HTTPException(422, 'Provide 1–500 questions per import.')
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            ids = [insert_question(c, q.model_dump()) for q in payload]
            c.commit()
        except ValueError as e:
            c.rollback()
            raise HTTPException(422, str(e)) from e
        except Exception:
            c.rollback()
            raise
    return {'imported':len(ids)}


@app.patch('/api/v3/teacher/questions/{question_id}')
def teacher_toggle_question(question_id: str, active: bool, context=Depends(teacher_write)):
    with database() as c:
        cur = c.execute('UPDATE questions SET active=? WHERE id=?', (int(active),question_id))
    if not cur.rowcount:
        raise HTTPException(404, 'Question not found.')
    return {'id':question_id,'active':active}


@app.get('/')
def home():
    return FileResponse(ROOT / 'frontend' / 'index.html')


app.mount('/static', StaticFiles(directory=ROOT / 'frontend'), name='static')
