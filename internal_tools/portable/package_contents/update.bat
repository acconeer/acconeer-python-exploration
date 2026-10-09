@echo off

echo Checking if uv is installed ...

uv --version

IF %ERRORLEVEL% EQU 0 GOTO :uv_present

echo Trying to install uv with winget ...

winget install --id=astral-sh.uv -e

IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Could not install uv, see above
    pause
    exit 1
)

echo INFO: Successfully installed uv, please rerun 'update.bat'
pause
exit 0

:uv_present

echo Updating timestamp in 'update_timestamp.txt' ...

REM The redirect creates the file even if uvx fails, so write it aside first
uvx python -c "import datetime; print(datetime.date.today())" >update_timestamp.tmp

IF %ERRORLEVEL% NEQ 0 (
    del update_timestamp.tmp
    echo ERROR: Could not create timestamp, see above
    echo INFO: #######################################################
    echo INFO: #                                                     #
    echo INFO: #  In order to proceed:                               #
    echo INFO: #                                                     #
    echo INFO: #      - if uv was just installed, make sure          #
    echo INFO: #        it's on PATH and run 'update.bat' again      #
    echo INFO: #      - if this persists, run 'uninstall_uv.bat'     #
    echo INFO: #                                                     #
    echo INFO: #######################################################
    pause
    exit 1
)

move /Y update_timestamp.tmp update_timestamp.txt >nul

echo INFO: #######################################################
echo INFO: #                                                     #
echo INFO: #  Update done! You can now:                          #
echo INFO: #                                                     #
echo INFO: #      - run 'run_app.bat' to launch the app          #
echo INFO: #      - run 'cmd_in_venv.bat' for a venv shell       #
echo INFO: #                                                     #
echo INFO: #######################################################

pause
