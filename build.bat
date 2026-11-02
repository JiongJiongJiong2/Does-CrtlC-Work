@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create .venv and install requirements-build.txt first.
  exit /b 1
)
echo Building DoesCtrlCWork from the version-controlled slimming spec...
".venv\Scripts\python.exe" tools\generate_version.py
if errorlevel 1 exit /b %errorlevel%
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean DoesCtrlCWork.spec
if errorlevel 1 exit /b %errorlevel%
echo.
echo Build complete! Output: dist\DoesCtrlCWork.exe
