@echo off
REM Save current directory
set "orig_dir=%CD%"

REM Change to Python 3.7.6 environment directory
cd /d C:\Envs\py3120env

REM Activate the virtual environment (adjust based on your env setup)
callgit init Scripts\activate.bat

REM Return to original directory
cd /d "%orig_dir%"

REM Load local project env overrides if present
if exist "%~dp0\.env.bat" call "%~dp0\.env.bat"

REM Pause so you can see the result
cmd
# Testing GitHub push