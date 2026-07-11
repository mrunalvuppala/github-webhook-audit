@echo off
title AgentAuditAI - Restart
cd /d "%~dp0"

echo.
echo  Restarting AgentAuditAI...
echo.

if not exist ".env" (
    copy .env.example .env >nul
    echo Created .env from .env.example
)

echo Stopping old containers...
docker compose down 2>nul

echo Stopping stale Python processes on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Starting PostgreSQL + Redis + Web + Worker...
echo.
echo  UI:      http://localhost:8000
echo  API docs http://localhost:8000/docs
echo.
echo  Press Ctrl+C to stop.
echo.

docker compose up --build
