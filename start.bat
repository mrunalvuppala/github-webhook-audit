@echo off
title AgentAuditAI - Startup
cd /d "%~dp0"

echo.
echo  ============================================
echo    AgentAuditAI - GitHub Webhook Auditor
echo  ============================================
echo.

if not exist ".env" (
    echo Creating .env from .env.example ...
    copy .env.example .env >nul
    echo.
    echo  NOTE: Using demo defaults. Edit .env for production.
    echo.
)

echo Starting Redis + API + Worker with Docker ...
echo.
echo  API docs:  http://localhost:8000/docs
echo  Webhook:   http://localhost:8000/v1/webhooks/github
echo.
echo  Press Ctrl+C to stop all services.
echo.

docker compose up --build
