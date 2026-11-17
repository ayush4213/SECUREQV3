-- Version 3 additions. Existing questions, options, and v2 session tables are untouched.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
  name TEXT NOT NULL,
  email TEXT COLLATE NOCASE UNIQUE,
  roll_number TEXT COLLATE NOCASE UNIQUE,
  password_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK ((role='teacher' AND email IS NOT NULL AND roll_number IS NULL)
      OR (role='student' AND roll_number IS NOT NULL AND email IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_users_students ON users(role, created_by, roll_number);

CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);

CREATE TABLE IF NOT EXISTS v3_exams (
  id TEXT PRIMARY KEY,
  teacher_id TEXT NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  subject TEXT NOT NULL,
  topic TEXT NOT NULL DEFAULT '',
  question_count INTEGER NOT NULL CHECK(question_count BETWEEN 1 AND 40),
  duration_minutes INTEGER NOT NULL CHECK(duration_minutes BETWEEN 1 AND 180),
  marks_per_question REAL NOT NULL CHECK(marks_per_question > 0),
  negative_marks REAL NOT NULL DEFAULT 0 CHECK(negative_marks >= 0),
  scheduled_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_v3_exams_teacher ON v3_exams(teacher_id, created_at);

CREATE TABLE IF NOT EXISTS v3_paper_sets (
  id TEXT PRIMARY KEY,
  exam_id TEXT NOT NULL REFERENCES v3_exams(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  UNIQUE(exam_id, label)
);
CREATE TABLE IF NOT EXISTS v3_set_questions (
  set_id TEXT NOT NULL REFERENCES v3_paper_sets(id) ON DELETE CASCADE,
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  position INTEGER NOT NULL,
  PRIMARY KEY(set_id, question_id),
  UNIQUE(set_id, position)
);

CREATE TABLE IF NOT EXISTS v3_assignments (
  id TEXT PRIMARY KEY,
  exam_id TEXT NOT NULL REFERENCES v3_exams(id) ON DELETE CASCADE,
  student_id TEXT NOT NULL REFERENCES users(id),
  set_id TEXT NOT NULL REFERENCES v3_paper_sets(id),
  assigned_at TEXT NOT NULL,
  UNIQUE(exam_id, student_id)
);
CREATE INDEX IF NOT EXISTS idx_v3_assignments_student ON v3_assignments(student_id);
CREATE INDEX IF NOT EXISTS idx_v3_assignments_exam ON v3_assignments(exam_id);

CREATE TABLE IF NOT EXISTS v3_attempts (
  id TEXT PRIMARY KEY,
  student_id TEXT NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL CHECK(kind IN ('practice', 'exam')),
  assignment_id TEXT UNIQUE REFERENCES v3_assignments(id),
  title TEXT NOT NULL,
  subject TEXT NOT NULL,
  topic TEXT NOT NULL DEFAULT '',
  marks_per_question REAL NOT NULL,
  negative_marks REAL NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  deadline_at TEXT NOT NULL,
  submitted_at TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','submitted')),
  score REAL,
  correct_count INTEGER,
  total_questions INTEGER NOT NULL,
  CHECK ((kind='practice' AND assignment_id IS NULL)
      OR (kind='exam' AND assignment_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_v3_attempt_student ON v3_attempts(student_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_v3_attempt_deadline ON v3_attempts(status, deadline_at);

CREATE TABLE IF NOT EXISTS v3_attempt_items (
  attempt_id TEXT NOT NULL REFERENCES v3_attempts(id) ON DELETE CASCADE,
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  position INTEGER NOT NULL,
  PRIMARY KEY(attempt_id, question_id),
  UNIQUE(attempt_id, position)
);
CREATE TABLE IF NOT EXISTS v3_attempt_options (
  attempt_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  option_id TEXT NOT NULL REFERENCES question_options(id),
  position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 3),
  PRIMARY KEY(attempt_id, question_id, position),
  UNIQUE(attempt_id, question_id, option_id),
  FOREIGN KEY(attempt_id, question_id) REFERENCES v3_attempt_items(attempt_id, question_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS v3_attempt_answers (
  attempt_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  option_id TEXT NOT NULL,
  answered_at TEXT NOT NULL,
  PRIMARY KEY(attempt_id, question_id),
  FOREIGN KEY(attempt_id, question_id, option_id)
     REFERENCES v3_attempt_options(attempt_id, question_id, option_id) ON DELETE RESTRICT
);
