@echo off

tools\python-3.9.10-embed-amd64\python.exe -c "import acconeer.exptool" 2> nul

if %errorlevel% neq 0 (
    echo Could not find acconeer.exptool
    echo Did you forget to run update.bat?
    echo.
    pause
    exit
)

tools\python-3.9.10-embed-amd64\python.exe -m acconeer.exptool.app --portable

if %errorlevel% neq 0 (
    pause
)
