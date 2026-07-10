@echo off
title Download AgentAuditAI Documentation
cd /d "%~dp0"

set DEST=%USERPROFILE%\Desktop\AgentAuditAI_Project_Documentation.md

copy /Y "docs\PROJECT_DOCUMENTATION.md" "%DEST%" >nul

echo.
echo  Documentation copied to your Desktop:
echo.
echo    %DEST%
echo.
echo  Opening now...
echo.

start "" "%DEST%"
pause
