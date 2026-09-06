param([ValidateRange(0,1)][int]$FastICacheHit = 0, [ValidateRange(0,1)][int]$LoadUseBubble = 0, [switch]$ValidationRun, [ValidateRange(0,4000)][int]$ConsoleDelayCycles = 0, [ValidateRange(0,1)][int]$Predictor = 1, [ValidateRange(1,8)][int]$CacheSetBits = 4, [ValidateRange(0,1)][int]$CacheEnabled = 1, [ValidateSet(27000000,54000000,60000000,67500000,72000000,75600000,81000000,90000000,99000000,102600000,108000000,135000000,162000000,180000000,194400000,216000000,270000000)][int]$ClockHz = 27000000)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    & ([System.IO.Path]::Combine($PSScriptRoot, 'build_coremark.ps1')) -Iterations 1 -ValidationRun:$ValidationRun -ConsoleDelayCycles $ConsoleDelayCycles -ClockHz $ClockHz
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark build failed.' }
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $manifest = Get-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','coremark-latest.json')) -Raw | ConvertFrom-Json
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $sources = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($project,'rtl')) -Filter '*.sv' | Sort-Object Name | ForEach-Object { "$linuxProject/rtl/$($_.Name)" }) + @("$linuxProject/sim/coremark_tb.sv")
    $runName = $manifest.RunName
    $firmwareName = $runName
    $runName += "_bp${Predictor}_cs${CacheSetBits}_cache$CacheEnabled"
    if ($LoadUseBubble) { $runName += '_loadbubble' }
    if ($FastICacheHit) { $runName += '_fastihit' }
    $firmwareSource = [System.IO.Path]::Combine($project,'build',"$firmwareName.hex")
    $firmwareSnapshot = [System.IO.Path]::Combine($project,'build',"$runName.hex")
    Copy-Item -LiteralPath $firmwareSource -Destination $firmwareSnapshot -Force
    $runManifest = [ordered]@{ RunName=$runName; FirmwareSha256=(Get-FileHash -LiteralPath $firmwareSnapshot -Algorithm SHA256).Hash; CacheEnabled=$CacheEnabled; Predictor=$Predictor; CacheSetBits=$CacheSetBits; StartedUtc=[datetime]::UtcNow.ToString('o') }
    $runManifest['FirmwareClockHz'] = $ClockHz
    $runManifest['LoadUseBubble'] = $LoadUseBubble
    $runManifest['FastICacheHit'] = $FastICacheHit
    $runManifest['SimulationClockHz'] = 100000000
    $runManifest['UartModelClockHz'] = 3200
    $runManifest | ConvertTo-Json | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build',"$runName.run.json")) -Encoding utf8BOM
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s coremark_tb "-Pcoremark_tb.ENABLE_PREDICTOR=$Predictor" "-Pcoremark_tb.CACHE_SET_BITS=$CacheSetBits" "-Pcoremark_tb.ENABLE_CACHE=$CacheEnabled" "-Pcoremark_tb.LOAD_USE_BUBBLE=$LoadUseBubble" "-Pcoremark_tb.FAST_ICACHE_HIT=$FastICacheHit" -o "$linuxProject/build/$runName.vvp" @sources
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark simulation compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linuxProject/build/$runName.vvp" "+firmware=$linuxProject/build/$runName.hex" "+uart=$linuxProject/build/$runName.uart"
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark simulation failed.' }
    $configuration = (0x0e020000 -bor ($CacheSetBits -shl 8) -bor $Predictor -bor ((1 - $CacheEnabled) -shl 1) -bor ($LoadUseBubble -shl 2) -bor (($FastICacheHit -band $CacheEnabled) -shl 3)).ToString('x8')
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/check_coremark.py" "$linuxProject/build/$runName.uart" --allow-short --clock-hz $ClockHz --expected-config $configuration --json "$linuxProject/build/$runName.result.json"
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark short-run CRC or metadata check failed.' }
    Write-Output 'PASS CoreMark short-run CRC; duration is not valid for scoring.'
} catch {
    Write-Error $_
    exit 1
}
