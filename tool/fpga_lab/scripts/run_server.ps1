#!/usr/bin/env pwsh
# Start the fpga-lab bridge server on 127.0.0.1:8600.
# NOTE: if launched in background/scheduled, the process may be killed after ~2 min by some
# shells; run it in the foreground of a dedicated terminal, or use a 600000 ms background timeout.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot           # fpga_lab/
Set-Location $root
python -m uvicorn fpga_lab_server.app:create_app --factory --host 127.0.0.1 --port 8600
