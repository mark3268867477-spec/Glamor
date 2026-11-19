@echo off
chcp 65001 >nul
setlocal

set "EXE=%~dp0release\Glamor_Portable\G'lamor.exe"
if exist "%EXE%" (
    start "" "%EXE%"
    exit /b 0
)

set "TOOLS=%~dp0tools"
set "PY="
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do (
    if not defined PY if exist %%~P (
        %%~P -c "import tkinter" >nul 2>nul && set "PY=%%~P"
    )
)

if not defined PY (
    echo [ERR] 未找到 G'lamor.exe 或带 tkinter 的 Python 环境。
    pause
    exit /b 1
)

for %%D in ("%PY%") do set "PYW=%%~dpDpythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "%TOOLS%\glam_studio.py"
) else (
    start "" "%PY%" "%TOOLS%\glam_studio.py"
)
exit /b 0