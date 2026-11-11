$ErrorActionPreference = 'Stop'
$logDir = Split-Path $MyInvocation.MyCommand.Path
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$logFile = Join-Path $logDir 'ftdi_heal_admin.log'
function Log($msg) { "$(Get-Date -Format 'HH:mm:ss') $msg" | Out-File $logFile -Append -Encoding UTF8 }

$before = [int]((Get-PnpDevice -PresentOnly -EA SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count)
Log "HEAL START  before_present=$before"

# 1. kill zombies
Get-Process cdt_js,cdt_cfg -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
if (Get-Process cdt_js,cdt_cfg -ErrorAction SilentlyContinue) { Log "  zombie cdt still alive after Stop" }
else { Log "  cdt_js/cdt_cfg zombies killed" }
Start-Sleep 1

# 2. scan + remove phantoms
& pnputil.exe /scan-devices 2>&1 | Out-Null
Start-Sleep 3

$phantoms = Get-PnpDevice -EA SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0403' }
$ids = @($phantoms | Select-Object -ExpandProperty InstanceId -Unique)
foreach ($id in $ids) {
    & pnputil.exe /remove-device $id 2>&1 | Out-Null
    Start-Sleep -Milliseconds 300
}
if ($ids.Count -gt 0) { Log "  removed $($ids.Count) phantom devnodes" }

# 3. final rescan
& pnputil.exe /scan-devices 2>&1 | Out-Null
Start-Sleep 8

$present = [int]((Get-PnpDevice -PresentOnly -EA SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count)
$total   = [int]((Get-PnpDevice -EA SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count)
Log "HEAL DONE   present=$present total=$total"

if ($present -gt 0) {
    $pdsRoot = if ($env:PDS_ROOT) { $env:PDS_ROOT } else { 'H:\GG\pango\PDS_2022.2-SP6.4' }
    $exe = Join-Path $pdsRoot 'bin\cdt_js.exe'
    $cdtAlive = [bool](Get-Process cdt_js -EA SilentlyContinue)
    if (-not $cdtAlive -and (Test-Path $exe)) {
        $proc = [System.Diagnostics.Process]::new()
        $proc.StartInfo.FileName = $exe
        $proc.StartInfo.Arguments = '-port 65420'
        $proc.StartInfo.UseShellExecute = $false
        $proc.StartInfo.CreateNoWindow = $true
        $null = $proc.Start()
        Log "  AUTO-START cdt_js PID=$($proc.Id)"
    } elseif ($cdtAlive) { Log "  cdt_js already alive" }
}
