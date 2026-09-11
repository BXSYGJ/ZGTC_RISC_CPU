param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$')][string]$StageName,
    [switch]$ValidationRun,
    [ValidateSet(0,2700000)][int]$ConsoleDelayCycles=2700000,
    [ValidateSet(2,3,4,5)][int]$PlacementSeed=2
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $root=[IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    $stage=[IO.Path]::Combine($root,'build','uart-timer-only',$StageName)
    $linuxStage=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $stage).Trim()
    if($LASTEXITCODE){throw 'WSL stage conversion failed'}
    $linuxAudit=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a ([IO.Path]::Combine($PSScriptRoot,'audit_short_pair.py'))).Trim()
    if($LASTEXITCODE){throw 'WSL auditor conversion failed'}
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $linuxAudit $linuxStage *> ([IO.Path]::Combine($stage,'short-audit.log'))
    if($LASTEXITCODE){throw 'Short-run nonregression/source audit rejected candidate'}
    $mode=[int][bool]$ValidationRun
    $delaySuffix=if($ConsoleDelayCycles -eq 0){''}else{'_p'+$ConsoleDelayCycles}
    $name='coremark_v'+$mode+'_i6000'+$delaySuffix+'_f157500000_rv32gcc_rv32im_O3_unroll_relax'
    $metadataPath=[IO.Path]::Combine($stage,'build',$name+'.build.json')
    if(-not (Test-Path -LiteralPath $metadataPath)){
        & pwsh -NoProfile -File ([IO.Path]::Combine($stage,'scripts','build_coremark.ps1')) -ClockHz 157500000 -Iterations 6000 -EnableM 1 -Optimization O3 -UnrollLoops -LinkerRelaxation -ConsoleDelayCycles $ConsoleDelayCycles -ValidationRun:$ValidationRun
        if($LASTEXITCODE){throw 'Full firmware compilation failed'}
    }
    $metadata=Get-Content -LiteralPath $metadataPath -Raw -Encoding utf8 | ConvertFrom-Json
    $firmware=[IO.Path]::Combine($stage,'build',$name+'.hex')
    if($metadata.ClockHz -ne 157500000 -or $metadata.Iterations -ne 6000 -or $metadata.ConsoleDelayCycles -ne $ConsoleDelayCycles -or $metadata.HexSha256 -ne (Get-FileHash -LiteralPath $firmware).Hash -or $metadata.ValidationRun -ne [bool]$ValidationRun){throw 'Firmware and PDS identity mismatch'}
    if(@(Get-Process -Name pds_shell -ErrorAction SilentlyContinue).Count){throw 'A PDS process is live; inspect it instead of starting another'}
    $run=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+([guid]::NewGuid().ToString('N').Substring(0,8))
    $log=[IO.Path]::Combine($stage,'build','pds-'+$run+'.log')
    & pwsh -NoProfile -File ([IO.Path]::Combine($stage,'scripts','run_pds.ps1')) -ClockHz 157500000 -PlacementSeed $PlacementSeed -UartProfile RemoteLab -UartBaud 115200 -FirmwareHex $firmware -Predictor 1 -CacheEnabled 1 -LoadUseBubble 1 -FastICacheHit 1 -FastDCacheRead 1 -FastDCacheWrite 1 -FetchOverlap 1 -DataOverlap 1 -EarlyDRequest 1 -EnableM 1 -CacheSetBits 6 -ICacheSetBits 9 -BtbIndexBits 8 *> $log
    if($LASTEXITCODE){throw ('157.5 MHz PDS rejected; preserve '+$log)}
    Write-Output ('157.5 MHz physical timing passed; full runtime and board qualification still required: '+$stage)
} catch { Write-Error $_; exit 1 }
