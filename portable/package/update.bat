@echo off
.\tools\python-3.9.10-embed-amd64\python.exe .\tools\update.py
echo.
if %errorlevel% equ 0 (
    echo All done!
) else (
    echo Update failed
)
echo.
pause
