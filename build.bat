@echo off
echo Building DoseCtrlC...
pip install pyinstaller -q
pyinstaller --name "DoseCtrlC" --onefile --windowed --icon app_icon.ico --clean main.py
echo.
echo Build complete! Output: dist\DoseCtrlC.exe
pause