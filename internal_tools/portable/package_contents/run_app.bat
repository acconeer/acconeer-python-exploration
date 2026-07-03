@echo off

IF NOT EXIST "update_timestamp.txt" (
    echo ERROR: File 'update_timestamp.txt' does not exist.
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

SET /P update_timestamp=<update_timestamp.txt

@echo on

uvx --python=3.12 --exclude-newer="%update_timestamp%" acconeer-exptool[app] --portable

@echo off

IF ERRORLEVEL 1 (
    echo ERROR: uvx or ET returned an error, see above
    pause
    exit 1
)
