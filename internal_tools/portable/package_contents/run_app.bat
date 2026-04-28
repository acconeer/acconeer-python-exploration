@echo off

IF NOT EXIST "update_timestamp.txt" (
    echo ERROR: File 'update_timestamp.txt' does not exist.
    echo ERROR: Run 'update.bat'.
    pause
    exit 1
)

SET /P update_timestamp=<update_timestamp.txt

@echo on

uvx --python=3.12 --exclude-newer=%update_timestamp% acconeer-exptool[app] --portable

@echo off

IF ERRORLEVEL 1 (
    echo ERROR: uvx or ET returned an error, see above
    pause
    exit 1
)
