[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $root=[IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    $baseline=[IO.Path]::Combine($root,'build','regfile-valid-fanout-stage')
    $snapshot=Get-Content -LiteralPath ([IO.Path]::Combine($baseline,'build','pds','20260909-124605-a402f7e8','source-snapshot.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if($snapshot.Files.Count -ne 20 -or $snapshot.Files['rtl/rv32_core.sv'] -ne 'DC90363D426754F032EC04DB6F4BE76DA439CCA149E372853EE2D64536D20FCE'){throw 'Wrong baseline source set'}
    foreach($relative in $snapshot.Files.Keys){if((Get-FileHash -LiteralPath ([IO.Path]::Combine($baseline,$relative))).Hash -ne $snapshot.Files[$relative]){throw ('Baseline changed: '+$relative)}}
    $run=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+([guid]::NewGuid().ToString('N').Substring(0,8))
    $stage=[IO.Path]::Combine($root,'build','uart-timer-only',$run)
    [void](New-Item -ItemType Directory -Path ([IO.Path]::Combine($stage,'build')))
    foreach($directory in @('rtl','sw','sim','scripts','constraints','fpga')){Copy-Item -LiteralPath ([IO.Path]::Combine($baseline,$directory)) -Destination ([IO.Path]::Combine($stage,$directory)) -Recurse}
    Copy-Item -LiteralPath ([IO.Path]::Combine($root,'build','coremark-upstream')) -Destination ([IO.Path]::Combine($stage,'build','coremark-upstream')) -Recurse
    Copy-Item -LiteralPath ([IO.Path]::Combine($baseline,'build','riscv32-toolchain.json')) -Destination ([IO.Path]::Combine($stage,'build','riscv32-toolchain.json'))
    Copy-Item -LiteralPath ([IO.Path]::Combine($PSScriptRoot,'rv32_peripherals.sv')) -Destination ([IO.Path]::Combine($stage,'rtl','rv32_peripherals.sv'))
    Copy-Item -LiteralPath ([IO.Path]::Combine($PSScriptRoot,'core_portme.c')) -Destination ([IO.Path]::Combine($stage,'sw','coremark','core_portme.c'))
    Copy-Item -LiteralPath ([IO.Path]::Combine($PSScriptRoot,'pds_soc_top_remote.v.in')) -Destination ([IO.Path]::Combine($stage,'scripts','pds_soc_top.v.in'))
    $configuration=Get-Content -LiteralPath ([IO.Path]::Combine($baseline,'build','configuration.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    $configuration.Purpose='UART/timer/performance services without GPIO; fixed 157.5 MHz screening only'
    $configuration.CandidatePeripheralsSha256=(Get-FileHash -LiteralPath ([IO.Path]::Combine($stage,'rtl','rv32_peripherals.sv'))).Hash
    $configuration | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([IO.Path]::Combine($stage,'build','configuration.json')) -Encoding utf8BOM
    $files=[ordered]@{}
    foreach($directory in @('rtl','sw','scripts','sim','fpga','constraints')){
        foreach($file in Get-ChildItem -LiteralPath ([IO.Path]::Combine($stage,$directory)) -Recurse -File){$relative=[IO.Path]::GetRelativePath($stage,$file.FullName).Replace([IO.Path]::DirectorySeparatorChar,'/');$files[$relative]=(Get-FileHash -LiteralPath $file.FullName).Hash}
    }
    [ordered]@{Schema=1;Stage=$stage;ClockHz=157500000;Baseline=$baseline;Files=$files;HardwareValidated=$false;ScoreQualified=$false} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath ([IO.Path]::Combine($stage,'input-binding.json')) -Encoding utf8BOM
    Write-Output ('UART/timer-only stage: '+$stage)
} catch { Write-Error $_; exit 1 }
