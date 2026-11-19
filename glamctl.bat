@echo off
chcp 65001 >nul
setlocal

set "TOOLS=%~dp0tools"
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

if not defined PY (
    echo [ERR] 未找到 Python 环境。
    exit /b 1
)

"%PY%" "%TOOLS%\glamctl.py" %*
exit /b %ERRORLEVEL%
