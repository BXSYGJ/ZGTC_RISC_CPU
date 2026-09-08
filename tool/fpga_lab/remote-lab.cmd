@echo off
rem remote-lab CLI wrapper (works from any directory).
rem Optional: pip install -e . provides the same `remote-lab` console command.
setlocal
set ROOT=%~dp0
cd /d "%ROOT%"
python -m fpga_lab_server.cli %*
exit /b %errorlevel%
