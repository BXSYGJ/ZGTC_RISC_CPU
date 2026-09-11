param([ValidateNotNullOrEmpty()][string]$PdsRoot = 'D:/PDS_2022.2-SP6.4')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $vendorModel = [System.IO.Path]::Combine($PdsRoot,'arch','vendor','pango','verilog','simulation','GTP_GPLL.v')
    if (-not (Test-Path -LiteralPath $vendorModel -PathType Leaf)) { throw 'Installed original PDS PLL model is required; it is not redistributed in this repository.' }
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE) { throw 'Project path conversion failed.' }
    $linuxModel = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $vendorModel).Trim()
    if ($LASTEXITCODE) { throw 'Vendor model path conversion failed.' }
    [void](New-Item -ItemType Directory -Path ([System.IO.Path]::Combine($project,'build')) -Force)
    $report = @()
    foreach ($frequency in @(54000000,60000000,67500000,72000000,75600000,81000000,90000000,99000000,102600000,108000000,120000000,126000000,132000000,135000000,162000000,180000000,194400000,216000000,270000000)) {
        $image = "$linuxProject/build/pll_$frequency.vvp"
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -s pll_tb "-Ppll_tb.CLOCK_HZ=$frequency" -o $image "$linuxProject/fpga/rv32_pll.sv" "$linuxProject/sim/pll_tb.sv" $linuxModel
        if ($LASTEXITCODE) { throw "PLL compile failed: $frequency" }
        $output = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/timeout --signal=TERM 60 /usr/bin/vvp $image
        if ($LASTEXITCODE -or ($output -join "`n") -match '(?i)error|fatal' -or ($output -join "`n") -notmatch "PASS PLL clock_hz=$frequency ") { throw "PLL frequency/reset test failed: $frequency" }
        $output | Write-Output
        $report += $output
    }
    $report | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','pll-tests.log')) -Encoding utf8BOM
} catch {
    Write-Error $_
    exit 1
}
