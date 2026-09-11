param([switch]$PhysicalOnly)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $root = [IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    $baseline = [IO.Path]::Combine($root,'build','regfile-valid-fanout-stage')
    $stage = [IO.Path]::Combine($root,'build','full-resource-opt-timer-keep-stage')
    $reference = Get-Content -LiteralPath ([IO.Path]::Combine($baseline,'build','pds','20260909-124605-a402f7e8','source-snapshot.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    $candidate = [IO.Path]::Combine($PSScriptRoot,'rv32_peripherals.sv')
    $files = [ordered]@{}
    if($reference.Files.Count -ne 20){throw 'Incomplete full-function baseline'}
    foreach($relative in $reference.Files.Keys){
        $expected = if($relative -eq 'rtl/rv32_peripherals.sv'){(Get-FileHash -LiteralPath $candidate).Hash}else{$reference.Files[$relative]}
        if((Get-FileHash -LiteralPath ([IO.Path]::Combine($stage,$relative))).Hash -ne $expected){throw ('Source mismatch: '+$relative)}
        $files[$relative]=$expected
    }
    if($files['rtl/rv32_core.sv'] -ne 'DC90363D426754F032EC04DB6F4BE76DA439CCA149E372853EE2D64536D20FCE'){throw 'Wrong CPU base'}
    $firmwareRoot = [IO.Path]::Combine($root,'build','wb-zero-157500-stage','build')
    $configuration = Get-Content -LiteralPath ([IO.Path]::Combine($baseline,'build','configuration.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    $configuration.CandidatePeripheralsSha256=$files['rtl/rv32_peripherals.sv']
    $configuration.Purpose='Complete GPIO/UART/timer; remove four synthesis attributes only. ILA insertion is required separately before promotion.'
    $configuration.SourceSnapshot=[ordered]@{Schema=1;Files=$files}
    $suitePath = [IO.Path]::Combine($PSScriptRoot,'test_full_peripherals.py')
    $linuxSuite = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $suitePath).Trim()
    if($LASTEXITCODE){throw 'WSL conversion failed'}
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $linuxSuite *> ([IO.Path]::Combine($stage,'build','full-peripherals-tests.log'))
    if($LASTEXITCODE){throw 'Complete-peripheral regression failed'}
    if(-not $PhysicalOnly){
        foreach($mode in @(0,1)){
            $name='coremark_v'+$mode+'_i10_f157500000_rv32gcc_rv32im_O3_unroll_relax'
            $metadataPath=[IO.Path]::Combine($firmwareRoot,$name+'.build.json')
            $metadata=Get-Content -LiteralPath $metadataPath -Raw -Encoding utf8 | ConvertFrom-Json
            $configuration.FirmwareSha256=$metadata.HexSha256
            $configPath=[IO.Path]::Combine($stage,'build','short-v'+$mode+'-configuration.json')
            if(Test-Path -LiteralPath $configPath){throw 'Short simulation already started; inspect its process and artifacts'}
            $configuration | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding utf8BOM
            $log=[IO.Path]::Combine($stage,'build','short-v'+$mode+'.log')
            & pwsh -NoProfile -File ([IO.Path]::Combine($stage,'scripts','run_coremark_compiled.ps1')) -ConfigurationManifest $configPath -FirmwareManifest $metadataPath -MaxCycles 50000000 -AllowShort *> $log
            if($LASTEXITCODE){throw ('Short simulation failed: '+$log)}
            Get-Content -LiteralPath $log -Tail 4
        }
    }
    $auditor=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a ([IO.Path]::Combine($PSScriptRoot,'qualify_short.py'))).Trim()
    if($LASTEXITCODE){throw 'Auditor path conversion failed'}
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $auditor
    if($LASTEXITCODE){throw 'Paired short source/cycle audit failed'}
    $firmware=[IO.Path]::Combine($firmwareRoot,'coremark_v0_i6000_p2700000_f157500000_rv32gcc_rv32im_O3_unroll_relax.hex')
    if((Get-FileHash -LiteralPath $firmware).Hash -ne '0E5EAD297589F9689CE8D9D60163DD7DD87FD71FF7EC11731545DE9CD9E99ABF'){throw 'Full baseline firmware mismatch'}
    if(@(Get-Process -Name pds_shell -ErrorAction SilentlyContinue).Count){throw 'PDS is live; inspect instead of restarting'}
    $log=[IO.Path]::Combine($stage,'build','pds-screen-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.log')
    & pwsh -NoProfile -File ([IO.Path]::Combine($stage,'scripts','run_pds.ps1')) -ClockHz 157500000 -PlacementSeed 2 -UartProfile RemoteLab -UartBaud 115200 -FirmwareHex $firmware -Predictor 1 -CacheEnabled 1 -LoadUseBubble 1 -FastICacheHit 1 -FastDCacheRead 1 -FastDCacheWrite 1 -FetchOverlap 1 -DataOverlap 1 -EarlyDRequest 1 -EnableM 1 -CacheSetBits 6 -ICacheSetBits 9 -BtbIndexBits 8 *> $log
    $result=$LASTEXITCODE
    Get-Content -LiteralPath $log -Tail 12
    if($result){throw 'Ordinary PDS did not qualify; preserve source netlist for a separately validated ILA insertion'}
    Write-Output 'Ordinary full-peripheral PDS passed; not yet an inserted-ILA performance result'
} catch { Write-Error $_; exit 1 }

