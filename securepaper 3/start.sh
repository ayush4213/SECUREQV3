#!/bin/sh
set -eu
# One application worker keeps SQLite write operations predictable.
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
