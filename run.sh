#!/usr/bin/env bash
set -e

echo "======================================================="
echo " Autonomous AI Research Assistant with Multi-Agent Collab"
echo "======================================================="

if [ ! -f ".venv/bin/python" ]; then
    echo "[INFO] Virtual environment not found. Creating .venv..."
    python3 -m venv .venv
    echo "[INFO] Installing dependencies..."
    .venv/bin/pip install -r requirements.txt
fi

echo "[INFO] Starting application server on http://127.0.0.1:8000..."
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
