@echo off
setlocal
cd /d "%~dp0"
echo Starting Enterprise Knowledge RAG...
docker compose build --quiet
if errorlevel 1 (
  echo Build failed.
  exit /b 1
)
docker compose up -d
if errorlevel 1 (
  echo Startup failed.
  exit /b 1
)
echo.
echo Started.
echo Frontend: http://localhost:5174
echo Backend health: http://localhost:8001/api/health
echo.
echo Use logs.bat to view logs, stop.bat to stop services.
