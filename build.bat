@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create .venv and install requirements-build.txt first.
  exit /b 1
)
echo Building DoesCtrlCWork from the version-controlled slimming spec...
echo Checking Windows discovery dependencies without starting the radio...
".venv\Scripts\python.exe" -c "from core.windows_nearby import _load_winrt; _load_winrt()"
if errorlevel 1 (
  echo Install or update requirements-build.txt before building.
  exit /b 1
)
".venv\Scripts\python.exe" tools\generate_version.py
if errorlevel 1 exit /b %errorlevel%
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean DoesCtrlCWork.spec
if errorlevel 1 exit /b %errorlevel%
echo.
echo Build complete! Output: dist\DoesCtrlCWork.exe
