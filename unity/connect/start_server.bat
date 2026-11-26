@echo off
chcp 65001 > nul
title [BCI Server] Live Explore EEG TCP Server

echo ======================================================================
echo   Contra Labs BCI // Unity TCP Server (Live Explore EEG Mode)
echo ======================================================================
echo.

set PYTHON_CMD=C:\Users\hsshi\miniconda3\envs\bci\python.exe

if not exist "%PYTHON_CMD%" (
    set PYTHON_CMD=python
)

set DEVICE=Explore_DABP
if not "%~1"=="" set DEVICE=%~1

echo [*] Target Device : %DEVICE%
echo [*] Subject Model : oyj
echo [*] Server Port   : 0.0.0.0:5000 (Local & Remote 2-PC Ready)
echo.

"%PYTHON_CMD%" "%~dp0bci_online_server.py" --subject oyj --model-dir "../../model" --device "%DEVICE%"

pause
