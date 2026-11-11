# ---------------------------------------------------------------------------
# FTDI Mild Recovery Loop — 无需管理员，后台每 60s 检查一次
# ---------------------------------------------------------------------------
param([int]$Minutes = 120)
$ErrorActionPreference = 'Continue'
$LogDir  = 'D:\0000\111\001\Pango\ZGTC_RISC_CPU\instrec_fpga\build\heal_logs'
$LogFile = Join-Path $LogDir 'ftdi_mild.log'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Log([string]$m) {
    $line = "{0} {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function FtdiCount {
    $out = & powershell -NoProfile -Command "(Get-PnpDevice -PresentOnly -EA SilentlyContinue | Where-Object {`$_.InstanceId -match 'VID_0403' } | Measure-Object).Count"
    try { return [int]($out.Trim().Split("`n")[-1]) } catch { return 0 }
}

function CdtJsAlive  { [bool](Get-Process cdt_js -ErrorAction SilentlyContinue) }
function CdtCfgAlive { [bool](Get-Process cdt_cfg -ErrorAction SilentlyContinue) }

$present    = FtdiCount
Log "=== FTDI mild recovery loop start (minutes=$Minutes)  VID_0403=$present ==="
$deadline   = (Get-Date).AddMinutes($Minutes)
$scan_count = 0

while ((Get-Date) -lt $deadline) {
    $n = FtdiCount
    if ($n -gt 0) {
        Log "VID_0403=$n present -> sleeping."
    } else {
        Log "VID_0403=0 -> T1(kill zombies) + T2(scan-devices)..."
        # T1
        if ((CdtJsAlive) -or (CdtCfgAlive)) {
            Log '  killing cdt_js / cdt_cfg ...'
            Get-Process cdt_js,cdt_cfg -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep 1
        }
        # T2
        $out = & pnputil.exe /scan-devices 2>&1 | Out-String
        Log ("  pnputil scan exit=$LASTEXITCODE  out=" + (($out -replace "`r`n", ' ') -replace '\s+', ' ').Trim().Substring(0, [Math]::Min(120, ($out -replace "`r`n", ' ').Length)))
        $scan_count++
        Start-Sleep 6
        $n2 = FtdiCount
        Log "  after scan: VID_0403=$n2  (scan_count=$scan_count)"
        if ($n2 -gt 0) {
            Log "!!! VID_0403 RECOVERED at $(Get-Date -Format 'HH:mm:ss') !!!"
            break
        }
    }
    Start-Sleep 55
}
Log "=== mild loop end ==="
