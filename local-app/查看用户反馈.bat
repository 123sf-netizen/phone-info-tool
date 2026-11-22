@echo off
cd /d "%~dp0"
docker compose exec -T backend python list_feedback.py
pause
