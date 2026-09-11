param([string]$FirmwareHex = '')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    if ([string]::IsNullOrWhiteSpace($FirmwareHex)) {
        & ([System.IO.Path]::Combine($PSScriptRoot, 'build_gpio.ps1'))
        if ($LASTEXITCODE) { throw 'GPIO firmware build failed.' }
        $manifest = Get-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', 'gpio-latest.json')) -Raw | ConvertFrom-Json
        $FirmwareHex = $manifest.Hex
    }
    $FirmwareHex = [System.IO.Path]::GetFullPath($FirmwareHex)
    if (-not (Test-Path -LiteralPath $FirmwareHex -PathType Leaf)) { throw 'GPIO firmware missing.' }
    $linux = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE) { throw 'Project path conversion failed.' }
    $linuxFirmware = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $FirmwareHex).Trim()
    if ($LASTEXITCODE) { throw 'Firmware path conversion failed.' }
    $run = [System.IO.Path]::Combine($project, 'build', 'gpio-tests', ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)))
    [void](New-Item -ItemType Directory -Path $run -Force)
    $linuxRun = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $run).Trim()
    if ($LASTEXITCODE) { throw 'Run path conversion failed.' }
    $sources = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($project, 'rtl')) -Filter '*.sv' | Sort-Object Name | ForEach-Object { "$linux/rtl/$($_.Name)" }) + @("$linux/sim/gpio_diagnostic_tb.sv")
    $inputs = [ordered]@{}
    $inputPaths = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($project, 'rtl')) -Filter '*.sv' | Select-Object -ExpandProperty FullName) + @([System.IO.Path]::Combine($project, 'sim', 'gpio_diagnostic_tb.sv'), $PSCommandPath, $FirmwareHex)
    foreach ($inputPath in $inputPaths) { $inputs[$inputPath] = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash }
    $record = [ordered]@{ Kind='RTL_SIMULATION_ONLY'; Firmware=$FirmwareHex; SourceHashes=$inputs; Passed=$false }
    $recordPath = [System.IO.Path]::Combine($run, 'result.json')
    $record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $recordPath -Encoding utf8BOM
    foreach ($configuration in @(0,1)) {
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s gpio_diagnostic_tb "-Pgpio_diagnostic_tb.FAST_CONFIGURATION=$configuration" -o "$linuxRun/gpio-$configuration.vvp" @sources
        if ($LASTEXITCODE) { throw 'GPIO test compilation failed.' }
        $result = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linuxRun/gpio-$configuration.vvp" "+firmware=$linuxFirmware"
        $testExit = $LASTEXITCODE
        $result | Set-Content -LiteralPath ([System.IO.Path]::Combine($run, "gpio-$configuration.log")) -Encoding utf8BOM
        $result | Write-Output
        if ($testExit -or -not ($result -match "^PASS gpio_diagnostic configuration=$configuration checks=")) { throw "GPIO diagnostic test failed: $configuration" }
    }
    foreach ($inputPath in $inputs.Keys) {
        if ($inputs[$inputPath] -ne (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash) { throw "Test input changed: $inputPath" }
    }
    $record.Passed = $true
    $record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $recordPath -Encoding utf8BOM
    Write-Output "PASS GPIO integration: $run"
} catch {
    Write-Error $_
    exit 1
}
