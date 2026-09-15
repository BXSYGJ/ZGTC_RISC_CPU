param([ValidateSet(0,1)][int[]]$ValidationRuns = @(0,1))
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    if ($ValidationRuns.Count -ne @($ValidationRuns | Sort-Object -Unique).Count) { throw 'Duplicate long-run firmware role.' }
    if ((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory -lt 6291456) { throw 'Insufficient commit headroom for long simulation.' }
    $running = @(Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" | Where-Object { $_.CommandLine -like '*full_fetch_commit_factored*run_coremark_compiled.py*' })
    if ($running.Count -ne 0) { throw 'A compiled simulation for this candidate is already running.' }
    & python ([IO.Path]::Combine($PSScriptRoot, 'audit_fetch_shorts.py'))
    if ($LASTEXITCODE -ne 0) { throw 'Source, firmware or short prerequisites failed.' }
    $linuxRoot = '/mnt/d/AAAFPGA/ZGTC_RISC_CPU/cpu/experiments/full_fetch_commit_factored'
    $firmwareRoot = [IO.Path]::Combine($linuxRoot, 'firmware').Replace([IO.Path]::DirectorySeparatorChar, '/')
    $runner = [IO.Path]::Combine($linuxRoot, 'scripts', 'run_coremark_compiled.py').Replace([IO.Path]::DirectorySeparatorChar, '/')
    $configuration = [IO.Path]::Combine($linuxRoot, 'configuration.json').Replace([IO.Path]::DirectorySeparatorChar, '/')
    foreach ($validation in $ValidationRuns) {
        $name = 'coremark_v' + $validation + '_i6000_p2700000_f153000000_rv32gcc_rv32im_O3_unroll_relax.build.json'
        $firmware = [IO.Path]::Combine($firmwareRoot, $name).Replace([IO.Path]::DirectorySeparatorChar, '/')
        $log = [IO.Path]::Combine($PSScriptRoot, 'build', ('long-v' + $validation + '-complete.log'))
        if (Test-Path -LiteralPath $log) { throw 'Completion attempt already exists; inspect its exact handle and evidence.' }
        & wsl.exe --exec python3 $runner --configuration $configuration --firmware-manifest $firmware --max-cycles 6000000000 2>&1 | Tee-Object -FilePath $log
        if ($LASTEXITCODE -ne 0) { throw ('Long simulation failed for V' + $validation + '; retain its artifacts.') }
    }
} catch {
    Write-Error $_
    exit 1
}
