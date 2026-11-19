@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
set "TOOLS=%ROOT%..\tools"
set "DIST=%ROOT%dist"

call :find_py
if not defined PY (
    echo [ERR] 未找到 Python 环境，请安装 Python 3 或 ESP-IDF Python。
    exit /b 1
)

"%PY%" "%TOOLS%\glamctl.py" build-all "%ROOT%apps" --dist "%DIST%"
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
