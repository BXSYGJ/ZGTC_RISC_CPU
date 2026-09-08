# Start the bridge server as a detached background process that survives this shell.
# Logs: sessions/server.log ; PID file: sessions/server.pid
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot          # fpga_lab/
$logDir = Join-Path $root 'sessions'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir 'server.log'
$pidFile = Join-Path $logDir 'server.pid'

# refuse double start
$conn = Get-NetTCPConnection -LocalPort 8600 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $p = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($p) { Write-Output "already running pid=$($p.Id)"; $p.Id | Out-File -Encoding ascii $pidFile; exit 0 }
}

Set-Location $root
$py = (Get-Command python).Source
$proc = Start-Process -FilePath $py -ArgumentList @(
    '-m','uvicorn','fpga_lab_server.app:create_app','--factory',
    '--host','127.0.0.1','--port','8600'
) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $log `
    -RedirectStandardError (Join-Path $logDir 'server.err.log') -PassThru
$proc.Id | Out-File -Encoding ascii $pidFile
Write-Output "started pid=$($proc.Id) log=$log"
