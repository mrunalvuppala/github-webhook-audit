@echo off
title Download AgentAuditAI Word Documentation
cd /d "%~dp0"

echo.
echo  Generating Word document with visual diagrams...
python scripts\generate_word_doc.py

echo.
echo  Opening document from your Desktop...
start "" "%USERPROFILE%\Desktop\AgentAuditAI_Project_Documentation.docx"
pause
