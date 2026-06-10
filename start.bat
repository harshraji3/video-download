@echo off
REM Quick start script for the oncology video processor
REM This opens two terminals - one for backend, one for frontend

echo.
echo ========================================
echo Oncology Video Processor - Quick Start
echo ========================================
echo.

REM Check if .env exists
if not exist .env (
    echo ERROR: .env file not found!
    echo Please create .env with your Azure connection string first.
    echo.
    echo Example:
    echo   AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
    echo   AZURE_STORAGE_CONTAINER=media-files
    echo.
    pause
    exit /b 1
)

echo [1/4] Installing Python dependencies...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)
echo ✓ Python dependencies installed

echo.
echo [2/4] Installing React dependencies...
cd clinsearch
call npm install --silent 2>nul
if errorlevel 1 (
    echo ERROR: Failed to install React dependencies
    pause
    exit /b 1
)
cd ..
echo ✓ React dependencies installed

echo.
echo [3/4] Starting FastAPI backend (port 8000)...
echo Opening new terminal for backend...
start "ClinSearch Backend" cmd /k "python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak

echo.
echo [4/4] Starting React frontend (port 3000)...
echo Opening new terminal for frontend...
start "ClinSearch Frontend" cmd /k "cd clinsearch && npm start"

echo.
echo ========================================
echo ✓ Services starting...
echo ========================================
echo.
echo Frontend:  http://localhost:3000
echo Backend:   http://localhost:8000
echo Health:    http://localhost:8000/health
echo.
echo Both terminals should open automatically.
echo If not, manually run:
echo   - Backend: python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
echo   - Frontend: cd clinsearch && npm start
echo.
pause
