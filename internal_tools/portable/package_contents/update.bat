@echo off

echo Checking if uv is installed ...

uv --version

IF ERRORLEVEL 1 (
    echo Trying to install uv with winget ...

    winget install --id=astral-sh.uv -e

    IF ERRORLEVEL 1 (
        echo ERROR: Could not install uv, see above
        pause
        exit 1
    )
)

echo Updating timestamp in 'update_timestamp.txt' ...

REM Treat a failed timestamp write as an update failure.
uvx python -c "import datetime; print(datetime.date.today())" >update_timestamp.txt || (
    echo ERROR: Could not create timestamp, see above
    echo
    echo NOTE: If this is your first time running the 'update.bat' script,
    echo NOTE: please try running 'update.bat' one more time.
    pause
    exit 1
)

echo
echo INFO:
echo INFO: Update done.
echo INFO:
echo INFO: Ready to run 'run_app.bat' or 'cmd_in_venv.bat'.
echo INFO:

pause
