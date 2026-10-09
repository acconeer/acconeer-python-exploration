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
    echo INFO: #                                                     #
    echo INFO: #######################################################
    pause
    exit 1
)

SET venvname=venv-%update_timestamp%

@echo on

uv venv --python=3.12 %venvname%

uv pip install --python=%venvname% --exclude-newer=%update_timestamp% acconeer-exptool[app]

@echo off

echo INFO:
echo INFO: Launching into virtual environment with Exploration Tool python package.
echo INFO: If additional Python packages are needed, install them with 'uv pip install numpy'
echo INFO:

cmd /k .\%venvname%\Scripts\activate
