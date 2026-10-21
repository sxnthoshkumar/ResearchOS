@echo off
setlocal

echo =======================================================
echo  Autonomous AI Research Assistant with Multi-Agent Collab
echo =======================================================

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Creating .venv...
    python -m venv .venv
    IF ERRORLEVEL 1 (
        echo [ERROR] Failed to create virtual environment. Ensure Python 3.10+ is installed.
        exit /b 1
    )
    echo [INFO] Installing dependencies...
    .venv\Scripts\pip.exe install -r requirements.txt
    IF ERRORLEVEL 1 (
        echo [ERROR] Failed to install dependencies.
        exit /b 1
    )
)

echo [INFO] Starting application server on http://127.0.0.1:8000...
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
