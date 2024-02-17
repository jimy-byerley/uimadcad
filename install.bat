@echo off
setlocal EnableDelayedExpansion

set arch=
set platform=windows
set prefix=

:parse_args
if "%1"=="" goto end_parse_args
if "%1"=="-a" (
    shift
    set arch=%1
    goto next_arg
)
if "%1"=="-h" (
    shift
    set platform=%1
    goto next_arg
)
if "%1"=="-p" (
    shift
    set prefix=%1
    goto next_arg
)
if "%1"=="-?" (
    echo build uimadcad and install it at the specified prefix path
    echo.
    echo usage: %~nx0 [-p PREFIX] [-a ARCH] [-h PLATFORM]
    exit /b 1
)

:next_arg
shift
goto parse_args

:end_parse_args

if "%arch%"=="" (
    set arch=x64
)

if "%prefix%"=="" (
    for /f "delims=" %%i in ('cd') do set "prefix=%%i\dist\%platform%_%arch%"
)

set data=%prefix%
set bin=%prefix%
set binformat=.exe

rem prepare directories
if not exist "%bin%" mkdir "%bin%"
if not exist "%data%" mkdir "%data%"

rem the common directories
if not exist "%data%\themes\" mkdir "%data%\themes\"
copy /y "%~dp0uimadcad\*.py" "%data%"
copy /y "%~dp0uimadcad\themes\*.qss" "%data%\themes\"
copy /y "%~dp0uimadcad\themes\*.yaml" "%data%\themes\"

rem platform specific
copy /y "%~dp0madcad.bat" "%bin%\"

if not exist "%prefix%\icons" mkdir "%prefix%\icons"
copy /y "%~dp0icons\*.svg" "%prefix%\icons\"
copy /y "%~dp0icons\*.ico" "%prefix%\"

:end_script
