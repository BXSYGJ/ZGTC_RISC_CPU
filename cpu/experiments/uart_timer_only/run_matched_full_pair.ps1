param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$')][string]$StageName)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $root=[IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    $stage=[IO.Path]::Combine($root,'build','uart-timer-only',$StageName)
    $linuxStage=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $stage).Trim()
    if($LASTEXITCODE){throw 'WSL stage conversion failed'}
    $linuxAudit=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a ([IO.Path]::Combine($PSScriptRoot,'audit_short_pair.py'))).Trim()
    if($LASTEXITCODE){throw 'WSL audit conversion failed'}
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $linuxAudit $linuxStage *> ([IO.Path]::Combine($stage,'matched-runtime-entry.log'))
    if($LASTEXITCODE){throw 'Matched runtime source/short gate rejected'}
    $binding=Get-Content -LiteralPath ([IO.Path]::Combine($stage,'input-binding.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    $files=[ordered]@{}
    foreach($relative in $binding.Files.Keys){
        if($relative.StartsWith('rtl/') -or $relative.StartsWith('fpga/') -or $relative.StartsWith('constraints/')){$files[$relative]=$binding.Files[$relative]}
    }
    foreach($validation in @($false,$true)){
        $mode=[int]$validation
        $name='coremark_v'+$mode+'_i6000_p2700000_f157500000_rv32gcc_rv32im_O3_unroll_relax'
        $metadataPath=[IO.Path]::Combine($stage,'build',$name+'.build.json')
        if(-not (Test-Path -LiteralPath $metadataPath)){
            & pwsh -NoProfile -File ([IO.Path]::Combine($stage,'scripts','build_coremark.ps1')) -ClockHz 157500000 -Iterations 6000 -EnableM 1 -Optimization O3 -UnrollLoops -LinkerRelaxation -ConsoleDelayCycles 2700000 -ValidationRun:$validation
            if($LASTEXITCODE){throw 'Matched full firmware build failed'}
        }
        $metadata=Get-Content -LiteralPath $metadataPath -Raw -Encoding utf8 | ConvertFrom-Json
        $firmware=[IO.Path]::Combine($stage,'build',$name+'.hex')
        if($metadata.ClockHz -ne 157500000 -or $metadata.ConsoleDelayCycles -ne 2700000 -or $metadata.Iterations -ne 6000 -or $metadata.ValidationRun -ne $validation -or (Get-FileHash -LiteralPath $firmware).Hash -ne $metadata.HexSha256){throw 'Matched full firmware metadata mismatch'}
        $config=Get-Content -LiteralPath ([IO.Path]::Combine($stage,'build','configuration.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
        $config.SourceSnapshot=[ordered]@{Schema=1;Files=$files}
        $config.FirmwareSha256=$metadata.HexSha256
        $config.Purpose='Full run with the accepted console/compiler layout; staged source binding, not PDS acceptance'
        $configPath=[IO.Path]::Combine($stage,'build','runtime-matched-v'+$mode+'-configuration.json')
        if(Test-Path -LiteralPath $configPath){throw 'Matched run already started; inspect actual process and artifacts before restarting'}
        $config | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $configPath -Encoding utf8BOM
        & pwsh -NoProfile -File ([IO.Path]::Combine($stage,'scripts','run_coremark_compiled.ps1')) -ConfigurationManifest $configPath -FirmwareManifest $metadataPath -MaxCycles 6000000000
        if($LASTEXITCODE){throw 'Matched full CoreMark runtime failed'}
    }
    Write-Output 'Matched full simulations finished; physical/board score qualification is separate'
} catch { Write-Error $_; exit 1 }
