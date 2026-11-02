@echo off
setlocal
set "WAVY_CONNECTION_ACTION=%~1"
if not defined WAVY_CONNECTION_ACTION set "WAVY_CONNECTION_ACTION=check"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Wavy-Connections.ps1" -Action "%WAVY_CONNECTION_ACTION%" -ConfigPath "%~dp0connections.json"
exit /b %errorlevel%
