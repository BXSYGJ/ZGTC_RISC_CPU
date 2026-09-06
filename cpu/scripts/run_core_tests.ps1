param([ValidateRange(1,8)][int]$BtbIndexBits = 4, [switch]$EarlyDRequest)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    & ([System.IO.Path]::Combine($PSScriptRoot, 'build_selftest.ps1'))
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed.' }
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $sources = @('rtl/rv32_core.sv', 'rtl/rv32_machine.sv', 'rtl/rv32_decode.sv', 'rtl/rv32_alu.sv', 'rtl/rv32_btb.sv', 'rtl/rv32_muldiv.sv', 'sim/core_tb.sv') | ForEach-Object { "$linuxProject/$_" }
    $allOutput = [System.Collections.Generic.List[string]]::new()
    $earlyData = if ($EarlyDRequest) { 1 } else { 0 }
    $variant = if ($EarlyDRequest) { '_earlydreq' } else { '' }
    if ($BtbIndexBits -ne 4) { $variant += "_btb$BtbIndexBits" }
    foreach ($predictor in @(0, 1)) {
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s core_tb "-Pcore_tb.BTB_INDEX_BITS=$BtbIndexBits" "-Pcore_tb.EARLY_D_REQUEST=$earlyData" "-Pcore_tb.PREDICTOR=$predictor" -o "$linuxProject/build/core_${predictor}$variant.vvp" @sources
        if ($LASTEXITCODE -ne 0) { throw 'CPU simulation compilation failed.' }
        foreach ($seed in @('12345678', 'a5a5c3c3', 'deadbeef')) {
            $runName = "core_p${predictor}_$seed$variant"
            $testOutput = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linuxProject/build/core_${predictor}$variant.vvp" "+firmware=$linuxProject/build/core_selftest.hex" "+trace=$linuxProject/build/$runName.trace" "+memory_out=$linuxProject/build/$runName.memory" "+seed=$seed"
            $testExitCode = $LASTEXITCODE
            $testOutput | ForEach-Object { $allOutput.Add("${runName}: $_"); Write-Output $_ }
            $allOutput | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', "core-tests$variant.log")) -Encoding utf8BOM
            if ($testExitCode -ne 0 -or -not ($testOutput -match '^PASS core checks=')) { throw "CPU self-test failed: $runName" }
            $referenceOutput = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/check_trace.py" "$linuxProject/build/core_selftest.bin" "$linuxProject/build/$runName.trace" --memory "$linuxProject/build/$runName.memory"
            if ($LASTEXITCODE -ne 0) { throw "Independent trace comparison failed: $runName" }
            $referenceOutput | ForEach-Object { $allOutput.Add([string]$_); Write-Output $_ }
            $allOutput | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', "core-tests$variant.log")) -Encoding utf8BOM
        }
    }
} catch {
    Write-Error $_
    exit 1
}
