@echo off
title AgentAuditAI - Live Demo
cd /d "%~dp0\.."

echo.
echo  Running live presentation demo ...
echo.

python scripts\demo.py
pause
