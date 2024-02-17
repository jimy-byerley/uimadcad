@echo off
setlocal

rem Set PYTHONPATH to include the directory of this batch file.
set "SCRIPT_DIR=%~dp0"
set PYTHONPATH=%PYTHONPATH%;%SCRIPT_DIR%

rem Execute the Python module, passing along any command-line arguments.
python -m uimadcad %*

endlocal
