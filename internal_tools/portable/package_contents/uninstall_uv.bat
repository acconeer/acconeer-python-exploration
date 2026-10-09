@echo off

echo Checking if uv is installed ...

uv --version

IF %ERRORLEVEL% NEQ 0 (
    echo INFO: Success! uv cannot be found on the system.
    echo INFO:          To reinstall, run the 'update.bat' script
    pause
    exit 0
)

echo Trying to uninstall uv with winget ...

winget uninstall --id=astral-sh.uv -e

IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: uv was not installed via winget.
    echo ERROR:
    echo ERROR: It seems like you have installed uv yourself outside this
    echo ERROR: portable ET distribution. You will need to uninstall your
    echo ERROR: custom installation yourself before proceeding
    pause
    exit 1
) ELSE (
    echo INFO: Success! uv was uninstalled.
    echo INFO:          To reinstall, run the 'update.bat' script
    pause
    exit 0
)
