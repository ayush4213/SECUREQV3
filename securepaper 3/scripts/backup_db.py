"""Create a consistent backup of the current SQLite database, including WAL data."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from backend.main import DB_PATH


def main():
    parser = argparse.ArgumentParser(description='Back up SecurePaper database safely')
    parser.add_argument('output', type=Path, help='Backup destination file')
    args = parser.parse_args()
    if not DB_PATH.is_file():
        parser.error(f'Database not found at {DB_PATH}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.resolve() == DB_PATH.resolve():
        parser.error('Backup path must differ from the active database.')
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(args.output) as target:
        source.backup(target)
    print(f'Backup saved: {args.output}')


if __name__ == '__main__':
    main()
