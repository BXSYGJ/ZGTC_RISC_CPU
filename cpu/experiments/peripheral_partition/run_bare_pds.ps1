param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$')][string]$BuildName,
    [ValidateSet(2,3,4,5)][int]$PlacementSeed=2,
    [ValidateSet(144000000,146250000,148500000,157500000)][int]$ClockHz=157500000
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $root=[IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    $firmwareBuild=[IO.Path]::Combine($root,'build','peripheral-partition',$BuildName)
    $firmware=[IO.Path]::Combine($firmwareBuild,'coremark.hex')
    $manifestPath=[IO.Path]::Combine($firmwareBuild,'manifest.json')
    $manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if($manifest.Profile -ne 'NoMmioPeripherals' -or $manifest.ClockHz -ne $ClockHz -or $manifest.Iterations -ne 6000){throw 'PDS requires a matching explicit 6000-iteration build'}
    $clockFlags=@($manifest.CompilerFlags | Where-Object { $_.StartsWith('-DCPU_CLOCK_HZ=') })
    if($clockFlags.Count -ne 1 -or $clockFlags[0] -ne ('-DCPU_CLOCK_HZ='+$ClockHz+'u')){throw 'Compiler and physical clock mismatch'}
    $firmwareHash=(Get-FileHash -LiteralPath $firmware).Hash
    if($firmwareHash -ne $manifest.FirmwareSha256){throw 'Bare firmware hash changed'}
    $metadata=Get-Content -LiteralPath ([IO.Path]::ChangeExtension($firmware,'.build.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    if($metadata.ClockHz -ne $ClockHz -or $metadata.HexSha256 -ne $firmwareHash -or $metadata.EnableM -ne 1){throw 'Firmware metadata does not match the build'}
    foreach($relative in $manifest.SourceHashes.Keys){
        $actual=if($relative.Contains('/')){[IO.Path]::Combine($root,$relative)}else{[IO.Path]::Combine($firmwareBuild,$relative)}
        if((Get-FileHash -LiteralPath $actual).Hash -ne $manifest.SourceHashes[$relative]){throw ('Captured source changed: '+$relative)}
    }
    $run=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+([guid]::NewGuid().ToString('N').Substring(0,8))
    $work=[IO.Path]::Combine($root,'build','peripheral-partition','pds',$run)
    $source=[IO.Path]::Combine($work,'source')
    foreach($directory in @('rtl','constraints','fpga','scripts')){[void](New-Item -ItemType Directory -Path ([IO.Path]::Combine($source,$directory)) -Force)}
    foreach($file in Get-ChildItem -LiteralPath $firmwareBuild -Filter '*.sv' -File){
        if($file.Name -eq 'coremark_bare_tb.sv'){continue}
        if($file.Name -in @('rv32_uart.sv','rv32_peripherals.sv','rv32_board_top.sv') -or -not $manifest.SourceHashes.ContainsKey($file.Name)){throw 'Unexpected bare RTL source'}
        Copy-Item -LiteralPath $file.FullName -Destination ([IO.Path]::Combine($source,'rtl',$file.Name))
    }
    $stage=[IO.Path]::Combine($root,'build','regfile-valid-fanout-stage','build','pds','20260909-124605-a402f7e8','source')
    Copy-Item -LiteralPath ([IO.Path]::Combine($stage,'fpga','rv32_pll.sv')) -Destination ([IO.Path]::Combine($source,'fpga','rv32_pll.sv'))
    foreach($file in Get-ChildItem -LiteralPath ([IO.Path]::Combine($stage,'constraints')) -Filter '*.fdc' -File){Copy-Item -LiteralPath $file.FullName -Destination ([IO.Path]::Combine($source,'constraints',$file.Name))}
    foreach($name in @('run_pds.ps1','build_pds.tcl','pds_report.py')){Copy-Item -LiteralPath ([IO.Path]::Combine($root,'build','regfile-valid-fanout-stage','scripts',$name)) -Destination ([IO.Path]::Combine($source,'scripts',$name))}
    Copy-Item -LiteralPath ([IO.Path]::Combine($PSScriptRoot,'pds_soc_top.v.in')) -Destination ([IO.Path]::Combine($source,'scripts','pds_soc_top.v.in'))
    [ordered]@{BuildName=$BuildName;ClockHz=$ClockHz;FirmwareSha256=$firmwareHash;SourceManifestSha256=(Get-FileHash -LiteralPath $manifestPath).Hash;MinimumNonregressingClockHz=157500000;ClockRegression=($ClockHz -lt 157500000);ScoreQualified=$false} | ConvertTo-Json | Set-Content -LiteralPath ([IO.Path]::Combine($work,'input-binding.json')) -Encoding utf8BOM
    $sourceScript=[IO.Path]::Combine($source,'scripts','run_pds.ps1')
    Push-Location ([IO.Path]::Combine($source,'scripts'))
    try {
        & pwsh -NoProfile -File $sourceScript -ClockHz $ClockHz -PlacementSeed $PlacementSeed -UartProfile Board -UartBaud 115200 -FirmwareHex $firmware -Predictor 1 -CacheEnabled 1 -LoadUseBubble 1 -FastICacheHit 1 -FastDCacheRead 1 -FastDCacheWrite 1 -FetchOverlap 1 -DataOverlap 1 -EarlyDRequest 1 -EnableM 1 -CacheSetBits 6 -ICacheSetBits 9 -BtbIndexBits 8 *> ([IO.Path]::Combine($work,'run.log'))
        $code=$LASTEXITCODE
    } finally { Pop-Location }
    if($code -ne 0){throw ('Bare PDS physical implementation rejected: '+$work)}
    $candidate=Get-ChildItem -LiteralPath ([IO.Path]::Combine($source,'build','pds')) -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if($null -eq $candidate){throw 'Bare PDS output directory missing'}
    Copy-Item -LiteralPath $candidate.FullName -Destination ([IO.Path]::Combine($work,'result')) -Recurse
    Write-Output ('Bare PDS timing passed; score and optimization acceptance remain unproven: '+$work)
    exit 0
} catch { Write-Error $_; exit 1 }

