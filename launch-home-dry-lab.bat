@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "API_DIR=%ROOT_DIR%apps\api"
set "WEB_DIR=%ROOT_DIR%apps\web"
set "API_PYTHON=%API_DIR%\.venv\Scripts\python.exe"

echo Home Dry Lab Content Machine launcher
echo.

if not exist "%API_PYTHON%" (
  echo [ERROR] API virtual environment not found at:
  echo         %API_PYTHON%
  echo.
  echo Create it first with:
  echo   cd apps\api
  echo   python -m venv .venv
  echo   .venv\Scripts\activate
  echo   pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "%WEB_DIR%\node_modules" (
  echo [ERROR] Web dependencies are not installed.
  echo.
  echo Install them first with:
  echo   cd apps\web
  echo   npm install
  pause
  exit /b 1
)

pushd "%API_DIR%" >nul
echo Applying database migrations...
call "%API_PYTHON%" -m alembic upgrade head
if errorlevel 1 (
  echo.
  echo [ERROR] Alembic migration failed. API and web were not started.
  popd >nul
  pause
  exit /b 1
)
popd >nul

echo Starting API on http://localhost:8000 ...
start "Home Dry Lab API" cmd /k "cd /d ""%API_DIR%"" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo Starting web app on http://localhost:3000 ...
start "Home Dry Lab Web" cmd /k "cd /d ""%WEB_DIR%"" && npm.cmd run dev"

echo Opening the app in your browser...
start "" "http://localhost:3000/dashboard"

echo.
echo Home Dry Lab Content Machine is launching.
echo - API: http://localhost:8000
echo - Web: http://localhost:3000/dashboard
echo.
echo Close the two terminal windows to stop the app.
exit /b 0
