@echo off

IF NOT EXIST "update_timestamp.txt" (
    echo ERROR: File 'update_timestamp.txt' does not exist.
    echo ERROR: Run 'update.bat'.
    pause
    exit 1
)

SET /P update_timestamp=<update_timestamp.txt
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
