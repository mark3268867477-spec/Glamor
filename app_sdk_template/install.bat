@echo off
chcp 65001 >nul
setlocal
REM Safe App Installer (NEVER touches OS Flash! Sends .gla to OS -> /sdcard/apps/)
REM Usage:
REM   install.bat all --port COM7
REM   install.bat com.glam.music --port COM7
REM   install.bat com.glam.music --wifi 192.168.1.50
REM   install.bat all --sdcard E:\

if "%~2"=="" (
    echo Usage: install.bat ^<app_id ^| all^> ^<--port COMx ^| --wifi IP ^| --sdcard DRIVE^> [target]
    echo Example: install.bat all --port COM7
    exit /b 1
)

set "APP_ID=%~1"
set "MODE=%~2"
set "TARGET=%~3"
set "ROOT=%~dp0"
set "TOOLS=%ROOT%..\tools"

call :find_py
if not defined PY (
    echo [ERR] 未找到 Python 环境。
    exit /b 1
)

call "%ROOT%build_apps.bat"
if errorlevel 1 exit /b 1

if /I "%APP_ID%"=="all" (
    for /d %%D in ("%ROOT%apps\*") do (
        if exist "%%~fD\manifest.json" (
            echo [INSTALL] Installing %%~nxD.gla ...
            "%PY%" "%TOOLS%\glamctl.py" install "%ROOT%dist\%%~nxD.gla" %MODE% "%TARGET%"
            if errorlevel 1 exit /b 1
        )
    )
) else (
    "%PY%" "%TOOLS%\glamctl.py" install "%ROOT%dist\%APP_ID%.gla" %MODE% "%TARGET%"
)
exit /b %ERRORLEVEL%

:find_py
set "PY="
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe"
) do (
    if not defined PY if exist %%~P set "PY=%%~P"
)
if not defined PY (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        echo "%%I" | findstr /I "WindowsApps" >nul || (
            if not defined PY set "PY=%%I"
        )
    )
)
exit /b 0
