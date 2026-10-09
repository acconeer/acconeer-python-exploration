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
    ) ELSE (
        echo INFO: Successfully installed uv, please rerun 'update.bat'
        pause
        exit 0
    )
)

echo Updating timestamp in 'update_timestamp.txt' ...

REM The redirect creates the file even if uvx fails, so write it aside first
uvx python -c "import datetime; print(datetime.date.today())" >update_timestamp.tmp

IF ERRORLEVEL 1 (
    del update_timestamp.tmp
    echo ERROR: Could not create timestamp, see above
    echo
    echo NOTE: If uv was just installed, make sure it is on PATH and try
    echo NOTE: running 'update.bat' again.
    pause
    exit 1
)

move /Y update_timestamp.tmp update_timestamp.txt >nul

echo
echo INFO:
echo INFO: Update done.
echo INFO:
echo INFO: Ready to run 'run_app.bat' or 'cmd_in_venv.bat'.
echo INFO:

pause
