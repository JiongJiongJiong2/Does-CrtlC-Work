@echo off
setlocal
echo Building DoesCtrlCWork from the version-controlled slimming spec...
python -m PyInstaller --noconfirm --clean DoesCtrlCWork.spec
if errorlevel 1 exit /b %errorlevel%
echo.
echo Build complete! Output: dist\DoesCtrlCWork.exe
