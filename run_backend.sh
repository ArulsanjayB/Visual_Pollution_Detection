#!/bin/bash
cd "$(dirname "$0")"
[ -d venv ] || { echo "[ERROR] Run ./setup.sh first"; exit 1; }
source venv/bin/activate
cd backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
