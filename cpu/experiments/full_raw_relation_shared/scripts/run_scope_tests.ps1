[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    & ([System.IO.Path]::Combine($PSScriptRoot,'build_scope.ps1')) -ConsoleDelayCycles 0 -SampleCycles 216 -TimeoutCycles 200000
    if ($LASTEXITCODE -ne 0) { throw 'Scope build failed.' }
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $manifest = Get-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','scope_p0_s216_t200000_rv32gcc.build.json')) -Raw | ConvertFrom-Json
    $linux = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $sources = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($project,'rtl')) -Filter '*.sv' | Sort-Object Name | ForEach-Object { "$linux/rtl/$($_.Name)" }) + @("$linux/sim/scope_tb.sv")
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s scope_tb -o "$linux/build/scope.vvp" @sources
    if ($LASTEXITCODE -ne 0) { throw 'Scope simulation compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linux/build/scope.vvp" "+firmware=$linux/build/$($manifest.RunName).hex" "+uart=$linux/build/scope.uart"
    if ($LASTEXITCODE -ne 0) { throw 'Scope simulation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linux/scripts/scope_decode.py" "$linux/build/scope.uart" --output "$linux/build/scope-simulation" --expect-uart 55 --verify-key
    if ($LASTEXITCODE -ne 0) { throw 'Scope checksum or waveform verification failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linux/scripts/test_scope_decode.py"
    if ($LASTEXITCODE -ne 0) { throw 'Scope decoder mutation tests failed.' }
} catch {
    Write-Error $_
    exit 1
}
