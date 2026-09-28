@echo off
chcp 65001 > nul
title [BCI Server] ML Pipeline Mock Streaming (Unity Ready)

echo ======================================================================
echo   Contra Labs BCI // Unity TCP Server (Mock ML Pipeline Mode)
echo ======================================================================
echo.
echo [*] Exploring conda environment...

set PYTHON_CMD=C:\Users\hsshi\miniconda3\envs\bci\python.exe

if not exist "%PYTHON_CMD%" (
    echo [!] Conda bci env python not found at %PYTHON_CMD%, falling back to system python...
    set PYTHON_CMD=python
)

echo [*] Server will listen on 0.0.0.0:5000 (Local & Remote 2-PC Ready)
echo.

"%PYTHON_CMD%" "%~dp0bci_online_server.py" --subject oyj --model-dir "../../model" --mock

pause
