@echo off
setlocal
cd /d "%~dp0"
echo Stopping Enterprise Knowledge RAG...
docker compose down
echo Stopped.
