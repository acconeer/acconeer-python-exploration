@echo off

SET update_timestamp=
IF EXIST "update_timestamp.txt" SET /P update_timestamp=<update_timestamp.txt

IF "%update_timestamp%"=="" (
    echo ERROR: File 'update_timestamp.txt' is missing or empty.
    echo INFO: #######################################################
    echo INFO: #                                                     #
    echo INFO: #  In order to proceed:                               #
    echo INFO: #                                                     #
    echo INFO: #      1. run the script 'update.bat'                 #
    echo INFO: #      2. run this script, 'run_app.bat', again       #
    echo INFO: #                                                     #
    echo INFO: #                                                     #
    echo INFO: #######################################################
    pause
    exit 1
)

REM Keep these uv arguments the same as update.bat's, which downloads them
uv run --offline --python=3.12 --exclude-newer="%update_timestamp%" --with "acconeer-exptool[app]" python -c ""

IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: The Exploration Tool as of %update_timestamp% is not downloaded
    echo INFO: #######################################################
    echo INFO: #                                                     #
    echo INFO: #  In order to proceed:                               #
    echo INFO: #                                                     #
    echo INFO: #      1. connect to the internet                     #
    echo INFO: #      2. run the script 'update.bat'                 #
    echo INFO: #      3. run this script, 'run_app.bat', again       #
    echo INFO: #                                                     #
    echo INFO: #######################################################
    pause
    exit 1
)

@echo on

uv run --offline --python=3.12 --exclude-newer="%update_timestamp%" --with "acconeer-exptool[app]" -m acconeer.exptool.app --portable

@echo off

IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: uvx or ET returned an error, see above
    echo INFO: #######################################################
    echo INFO: #                                                     #
    echo INFO: #  If this error persists:                            #
    echo INFO: #                                                     #
    echo INFO: #      1. remove the file 'update_timestamp.txt'      #
    echo INFO: #      2. run this script, 'run_app.bat', again       #
    echo INFO: #                                                     #
    echo INFO: #######################################################
    pause
    exit 1
)
