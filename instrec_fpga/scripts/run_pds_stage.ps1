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
    [ValidateSet('dev_map', 'pnr', 'report_timing', 'gen_bit_stream')][string]$From = 'pnr',
    [string]$TopModule = 'instrec_top',
    [string]$ProjectName = 'instrec_fpga'
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$run = (Resolve-Path $RunDir).Path

$requiredDirs = @('synthesize', 'compile')
if ($From -ne 'dev_map') { $requiredDirs += 'device_map' }
foreach ($need in $requiredDirs) {
    if (-not (Test-Path -LiteralPath (Join-Path $run $need))) {
        throw "stage directory '$need' is missing under $run; this run cannot be resumed"
    }
}

# The project file records the part and the design source list.  PDS creates a
# DEFAULT (fab_demo / PGL12G) project when a scripted flow starts without
# open_project, which silently discards the previous state -- that happened on
# the first use of this script.  Refuse to run against a wrong or missing
# project file instead of overwriting it.
$prj = Join-Path $run "$ProjectName.pds"
if (-not (Test-Path -LiteralPath $prj)) {
    throw "project file not found: $prj"
}
$prjText = [System.IO.File]::ReadAllText($prj)
if ($prjText -notmatch 'PG2L100H') {
    throw "project file does not describe PG2L100H (it was overwritten by a default project): $prj"
}

# PDS replaces the .pds with a default project as soon as the scripted run
# starts without a successfully opened project, so keep a copy and restore it
# if the resumed flow fails -- otherwise one typo destroys the netlist state.
$stamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
$prjBak = "$prj.$stamp.bak"
[System.IO.File]::WriteAllText($prjBak, $prjText, [System.Text.UTF8Encoding]::new($false))

$stages = @('dev_map', 'pnr', 'report_timing', 'gen_bit_stream')
$startIdx = [array]::IndexOf($stages, $From)
if ($startIdx -lt 0) { throw "unknown stage '$From'" }
$prjTcl = $prj.Replace('\', '/')
$body = "open_project {$prjTcl}`n" + (($stages[$startIdx..($stages.Count - 1)]) -join "`n") + "`nexit"

$tclPath = Join-Path $run ("stage-$stamp.tcl")
$logPath = Join-Path $run ("stage-$stamp.log")
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
if (@(Get-Process -Name pds_shell -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'A pds_shell process already exists; only one PDS build is allowed.'
}
$proc = Start-Process -FilePath $pdsShell -ArgumentList $args -PassThru -WindowStyle Hidden -Wait `
    -RedirectStandardOutput $logPath -RedirectStandardError (Join-Path $run ("stage-$stamp.stderr.log"))
Write-Output "PDS ExitCode: $($proc.ExitCode)"
if ($proc.ExitCode -ne 0) {
    [System.IO.File]::WriteAllText($prj, [System.IO.File]::ReadAllText($prjBak), [System.Text.UTF8Encoding]::new($false))
    throw "PDS exited with $($proc.ExitCode); project file restored from backup; see $logPath"
}
if (-not [System.IO.File]::ReadAllText($prj).Contains('PG2L100H')) {
    [System.IO.File]::WriteAllText($prj, [System.IO.File]::ReadAllText($prjBak), [System.Text.UTF8Encoding]::new($false))
    throw "PDS replaced the project file with a default one; restored from backup (open_project syntax still wrong)"
}

$stageOutput = [System.IO.File]::ReadAllText($logPath)
if ([regex]::IsMatch($stageOutput, '(?m)^E:')) {
    throw "PDS reported a tool error despite exit code 0; inspect $logPath"
}

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
