@echo off

if exist "acconeer-python-exploration" (
    tools\python-3.9.10-embed-amd64\python.exe -m acconeer.exptool.app
    pause
) else (
    echo Could not find acconeer-python-exploration
    echo Did you forget to run update.bat?
    echo.
    pause
)
