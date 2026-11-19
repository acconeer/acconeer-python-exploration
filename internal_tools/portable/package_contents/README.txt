This package contains a portable version of Acconeer Exploration Tool compatible
with Windows.

Included are scripts, based on Astral.sh's uv, which is used to create an isolated
and portable environment.

To use this package 'update.bat' must be used first and after that
'run_app.bat' can be used to run the Exploration Tool application.

'update.bat' needs an internet connection, as it downloads the Exploration
Tool. 'run_app.bat' does not: it starts what 'update.bat' downloaded.

Executable files included:
 * update.bat      - Used installation and updates
 * run_app.bat     - Start up the application
 * cmd_in_venv.bat - Start a command prompt configured to use an isolated
                     environment.
