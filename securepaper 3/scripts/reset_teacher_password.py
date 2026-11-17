"""Operator-only initial teacher password recovery from the server shell."""
from __future__ import annotations

import argparse
import getpass
import os
from backend.main import database, hash_password, stamp


def main():
    parser = argparse.ArgumentParser(description='Reset an existing teacher password')
    parser.add_argument('--email', default=os.environ.get('SECUREPAPER_TEACHER_EMAIL', 'teacher@securepaper.local'))
    args = parser.parse_args()
    password = os.environ.get('SECUREPAPER_TEACHER_PASSWORD') or getpass.getpass('New teacher password: ')
    secret = hash_password(password)
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute("SELECT id FROM users WHERE role='teacher' AND email=?", (args.email,)).fetchone()
        if not row:
            c.rollback()
            parser.error('Teacher account not found. Check the email address.')
        c.execute('UPDATE users SET password_hash=?,updated_at=? WHERE id=?', (secret, stamp(), row['id']))
        c.execute('DELETE FROM auth_sessions WHERE user_id=?', (row['id'],))
        c.commit()
    print('Teacher password updated. Existing login sessions were revoked.')


if __name__ == '__main__':
    main()
