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

@echo on

uvx --python=3.12 --exclude-newer="%update_timestamp%" acconeer-exptool[app] --portable

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
