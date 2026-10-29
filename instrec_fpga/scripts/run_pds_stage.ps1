# Re-run only the later PDS stages of an existing build directory.
#
# Why: a full rebuild of the InstRec system costs 1h20m~1h50m, of which
# compile + synthesize + dev_map take roughly 20-25 minutes and pnr takes
# the rest.  When only the *placement/routing* parameters change (router
# effort, seed, constraints that do not alter the netlist) the netlist is
# unchanged, so the front stages can be reused instead of recomputed.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_stage.ps1 `
#       -RunDir build/pds/20261029-191053-0849da3b -From pnr
#   ... -From report_timing        # bitstream exists, only refresh the report
#
# The script never deletes the source run; it writes a separate *.stage.tcl
# and *.stage.log into that directory and prints the produced bitstream.
# NOTE: this is NOT a substitute for a full build after an RTL change -- if
# any .v under src/ changed, use run_pds_full.ps1.

param(
    [Parameter(Mandatory = $true)][string]$RunDir,
    [ValidateSet('pnr', 'report_timing', 'gen_bit_stream')][string]$From = 'pnr',
    [string]$TopModule = 'instrec_top',
    [string]$ProjectName = 'instrec_fpga'
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$run = (Resolve-Path $RunDir).Path

foreach ($need in @('device_map', 'synthesize', 'compile')) {
    if (-not (Test-Path -LiteralPath (Join-Path $run $need))) {
        throw "stage directory '$need' is missing under $run; this run cannot be resumed"
    }
}

$stages = @('pnr', 'report_timing', 'gen_bit_stream')
$startIdx = [array]::IndexOf($stages, $From)
if ($startIdx -lt 0) { throw "unknown stage '$From'" }
$body = ($stages[$startIdx..($stages.Count - 1)]) -join "`n"

$tclPath = Join-Path $run 'stage.tcl'
$logPath = Join-Path $run 'stage.log'
$text = "# Resumed stage flow: $From -> gen_bit_stream (run $([System.IO.Path]::GetFileName($run)))`n$body`n"
[System.IO.File]::WriteAllText($tclPath, $text, [System.Text.UTF8Encoding]::new($false))

$pdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'Process')
if ([string]::IsNullOrWhiteSpace($pdsRoot)) { $pdsRoot = 'H:\GG\pango\PDS_2022.2-SP6.4' }
$pdsShell = [System.IO.Path]::Combine($pdsRoot, 'bin', 'pds_shell.exe')
if (-not (Test-Path -LiteralPath $pdsShell -PathType Leaf)) { throw "PDS shell not found: $pdsShell" }

$licenseFile = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
if ([string]::IsNullOrWhiteSpace($licenseFile)) { $licenseFile = 'E:\License\pango\new_pds_F4A80DA47D72.lic' }
$env:PANGO_LICENSE_FILE = $licenseFile

Write-Output "resume: $From -> gen_bit_stream"
Write-Output "run dir: $run"
$started = [datetime]::UtcNow
$args = @('-file', ('"' + $tclPath + '"'), '-work_dir', ('"' + $run + '"'), '-project_name', $ProjectName)
$proc = Start-Process -FilePath $pdsShell -ArgumentList $args -PassThru -WindowStyle Hidden -Wait `
    -RedirectStandardOutput $logPath -RedirectStandardError (Join-Path $run 'stage.stderr.log')
Write-Output "PDS ExitCode: $($proc.ExitCode)"
if ($proc.ExitCode -ne 0) { throw "PDS exited with $($proc.ExitCode); see $logPath" }

$bit = Join-Path $run ("generate_bitstream\$TopModule.sbit")
if (Test-Path -LiteralPath $bit) {
    $info = Get-Item -LiteralPath $bit
    if ($info.LastWriteTimeUtc -lt $started.AddSeconds(-1)) { throw "bitstream is stale: $bit" }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $fs = [System.IO.File]::OpenRead($bit)
    try { $bytes = $sha.ComputeHash($fs) } finally { $fs.Dispose(); $sha.Dispose() }
    $hex = ($bytes | ForEach-Object { $_.ToString('X2') }) -join ''
    Write-Output "bitstream: $bit"
    Write-Output "sha256: $hex"
} else {
    throw "no bitstream produced: $bit"
}

$rtr = Join-Path $run ("report_timing\$TopModule.rtr")
if (Test-Path -LiteralPath $rtr) { Write-Output "timing: $rtr" }