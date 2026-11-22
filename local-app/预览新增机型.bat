@echo off
cd /d "%~dp0"
docker compose exec -T backend python sync_seed.py
pause
