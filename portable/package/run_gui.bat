@echo off
if exist "acconeer-python-exploration\gui\main.py" (
    cd acconeer-python-exploration\gui
    ..\..\tools\python-3.7.4-embed-amd64\python.exe main.py
) else (
    echo Could not find acconeer-python-exploration\gui\main.py
    echo Did you forget to run update.bat?
    echo.
    pause
)
