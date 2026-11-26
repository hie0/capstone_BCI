@echo off
chcp 65001 > nul
title [BCI Server] Pure Dummy Simulation (Zero Dependencies)

echo ======================================================================
echo   Contra Labs BCI // Pure Dummy BCI Server
echo ======================================================================
echo.
echo [*] No dependencies required. Running with Python...

set PYTHON_CMD=C:\Users\hsshi\miniconda3\envs\bci\python.exe
if not exist "%PYTHON_CMD%" set PYTHON_CMD=python

"%PYTHON_CMD%" "%~dp0dummy_bci_server.py"

pause
