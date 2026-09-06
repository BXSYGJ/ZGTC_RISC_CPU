param([ValidateRange(0,1)][int]$FastICacheHit = 0, [ValidateRange(0,1)][int]$LoadUseBubble = 0, [switch]$ExternalUart, [ValidateRange(0,1)][int]$Predictor = 1, [ValidateRange(1,8)][int]$CacheSetBits = 4, [ValidateRange(0,1)][int]$CacheEnabled = 1)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    & ([System.IO.Path]::Combine($PSScriptRoot, 'build_soc.ps1')) -ExternalUart:$ExternalUart
    if ($LASTEXITCODE -ne 0) { throw 'SoC firmware build failed.' }
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $symbols = & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Nm "$linuxProject/build/soc_selftest.elf"
    if ($LASTEXITCODE -ne 0) { throw 'ELF symbol lookup failed.' }
    $bssStart = $null; $bssEnd = $null
    foreach ($line in $symbols) {
        if ($line -match '^([0-9a-fA-F]+)\s+\w\s+__bss_start$') { $bssStart = $Matches[1] }
        if ($line -match '^([0-9a-fA-F]+)\s+\w\s+__bss_end$') { $bssEnd = $Matches[1] }
    }
    if (-not $bssStart -or -not $bssEnd) { throw 'BSS symbols missing.' }
    $sources = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($project, 'rtl')) -Filter '*.sv' | Sort-Object Name | ForEach-Object { "$linuxProject/rtl/$($_.Name)" }) + @("$linuxProject/sim/soc_tb.sv")
    $allOutput = [System.Collections.Generic.List[string]]::new()
    $uartIrq = if ($ExternalUart) { 1 } else { 0 }
    foreach ($fault in @(0, 1)) {
        $runName = "soc_p${Predictor}_s${CacheSetBits}_uart_${uartIrq}_fault_${fault}_cache$CacheEnabled"
        if ($LoadUseBubble) { $runName += '_loadbubble' }
        if ($FastICacheHit) { $runName += '_fastihit' }
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s soc_tb "-Psoc_tb.FAULT_TEST=$fault" "-Psoc_tb.EXTERNAL_UART=$uartIrq" "-Psoc_tb.ENABLE_PREDICTOR=$Predictor" "-Psoc_tb.CACHE_SET_BITS=$CacheSetBits" "-Psoc_tb.ENABLE_CACHE=$CacheEnabled" "-Psoc_tb.LOAD_USE_BUBBLE=$LoadUseBubble" "-Psoc_tb.FAST_ICACHE_HIT=$FastICacheHit" -o "$linuxProject/build/$runName.vvp" @sources
        if ($LASTEXITCODE -ne 0) { throw 'SoC compilation failed.' }
        $result = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linuxProject/build/$runName.vvp" "+firmware=$linuxProject/build/soc_selftest.hex" "+trace=$linuxProject/build/$runName.trace" "+bss_start=$bssStart" "+bss_end=$bssEnd"
        $testExitCode = $LASTEXITCODE
        $result | ForEach-Object { $allOutput.Add([string]$_); Write-Output $_ }
        $logName = "soc-tests-p${Predictor}-s${CacheSetBits}-uart-${uartIrq}-cache$CacheEnabled"
        if ($LoadUseBubble) { $logName += '-loadbubble' }
        if ($FastICacheHit) { $logName += '-fastihit' }
        $allOutput | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', "$logName.log")) -Encoding utf8BOM
        if ($testExitCode -ne 0 -or -not ($result -match '^PASS soc(_fault)? checks=')) { throw "SoC test failed: $runName" }
    }
} catch {
    Write-Error $_
    exit 1
}
