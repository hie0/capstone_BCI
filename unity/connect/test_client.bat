@echo off
chcp 65001 > nul
title [BCI Client] Diagnostic Test Connection

set PYTHON_CMD=C:\Users\hsshi\miniconda3\envs\bci\python.exe
if not exist "%PYTHON_CMD%" set PYTHON_CMD=python

"%PYTHON_CMD%" "%~dp0test_connection.py"

pause
