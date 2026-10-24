param(
    [ValidateRange(0,1)][int]$EnableM = 1,
    [ValidateSet(9600,19200,38400,57600,115200)][int]$UartBaud = 115200
)
# One-button 100Pro+ CPU SoC build: bootloader hex -> PDS batch flow -> bitstream.
# No WSL, no GUI: native xPack toolchain + pds_shell.exe + cdt_cfg (download is
# a separate step, see program_full.tcl / test_scan.tcl).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $repoRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', '..'))
    $rtlRoot = [System.IO.Path]::Combine($repoRoot, 'cpu', 'rtl')

    # 1) bootloader firmware image (64 KB BRAM image, bootloader in first 4 KB)
    $bootHex = [System.IO.Path]::Combine($project, 'build', 'bootloader_100h.hex')
    & ([System.IO.Path]::Combine($PSScriptRoot, 'build_boot_100h.ps1')) -Out $bootHex
    if ($LASTEXITCODE -ne 0) { throw 'Bootloader build failed.' }

    # 2) build directory + source snapshot (hashes for provenance)
    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $buildRoot = [System.IO.Path]::Combine($project, 'build', 'pds', $runName)
    [void](New-Item -ItemType Directory -Path $buildRoot -Force)
    $fwHex = [System.IO.Path]::Combine($buildRoot, 'firmware.hex')
    Copy-Item -LiteralPath $bootHex -Destination $fwHex
    $fwHash = (Get-FileHash -LiteralPath $fwHex -Algorithm SHA256).Hash

    # 3) expand the top template (INIT_FILE points at the build-dir hex)
    $topTemplate = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($project, 'src', 'pds_cpu_top_100h.v.in'))
    $top = $topTemplate.Replace('__INIT_FILE__', $fwHex.Replace([System.IO.Path]::DirectorySeparatorChar, '/')).Replace('__ENABLE_M__', [string]$EnableM).Replace('__UART_BAUD__', [string]$UartBaud)
    $topSource = [System.IO.Path]::Combine($buildRoot, 'pds_cpu_top_100h.v')
    [System.IO.File]::WriteAllText($topSource, $top, [System.Text.UTF8Encoding]::new($false))

    # 4) expand the PDS TCL
    $tclTemplate = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($PSScriptRoot, 'build_full.tcl'))
    $scriptPath = [System.IO.Path]::Combine($buildRoot, 'build.tcl')
    $tcl = $tclTemplate.Replace('__RTL_ROOT__', $rtlRoot.Replace([System.IO.Path]::DirectorySeparatorChar, '/')).Replace('__PROJECT_ROOT__', $project.Replace([System.IO.Path]::DirectorySeparatorChar, '/')).Replace('__BUILD_ROOT__', $buildRoot.Replace([System.IO.Path]::DirectorySeparatorChar, '/')).Replace('__TOP_SOURCE__', $topSource.Replace([System.IO.Path]::DirectorySeparatorChar, '/'))
    [System.IO.File]::WriteAllText($scriptPath, $tcl, [System.Text.UTF8Encoding]::new($false))

    # 5) run PDS batch
    $pdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'Process')
    if ([string]::IsNullOrWhiteSpace($pdsRoot)) { $pdsRoot = [System.IO.Path]::Combine('H:', 'GG', 'pango', 'PDS_2022.2-SP6.4') }
    $pdsShell = [System.IO.Path]::Combine($pdsRoot, 'bin', 'pds_shell.exe')
    if (-not (Test-Path -LiteralPath $pdsShell -PathType Leaf)) { throw "PDS shell not found: $pdsShell" }
    $env:PANGO_LICENSE_FILE = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) { throw 'PANGO_LICENSE_FILE is not configured in the current user environment.' }

    $stdout = [System.IO.Path]::Combine($buildRoot, 'pds.stdout.log')
    $stderr = [System.IO.Path]::Combine($buildRoot, 'pds.stderr.log')
    $arguments = @('-file', ('"' + $scriptPath + '"'), '-work_dir', ('"' + $buildRoot + '"'), '-project_name', 'zgtc_100h')
    $started = [datetime]::UtcNow
    $process = Start-Process -FilePath $pdsShell -ArgumentList $arguments -PassThru -WindowStyle Hidden -Wait -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-Output "PDS PID: $($process.Id)"
    Write-Output "PDS build directory: $buildRoot"
    $outputText = [System.IO.File]::ReadAllText($stdout) + [System.IO.File]::ReadAllText($stderr)
    $outputText -split "`n" | Select-Object -Last 30 | Write-Output
    Write-Output "PDS ExitCode: $($process.ExitCode)"
    if ($process.ExitCode -ne 0 -or $outputText -match '(?m)^E:') { throw 'PDS reported failure; inspect the build logs.' }

    # 6) verify bitstream
    $bitstream = [System.IO.Path]::Combine($buildRoot, 'generate_bitstream', 'pds_cpu_top_100h.sbit')
    if (-not (Test-Path -LiteralPath $bitstream -PathType Leaf)) { throw 'PDS did not produce the expected bitstream.' }
    if ((Get-Item -LiteralPath $bitstream).LastWriteTimeUtc -lt $started.AddSeconds(-1)) { throw 'Bitstream is stale.' }
    $sbitHash = (Get-FileHash -LiteralPath $bitstream -Algorithm SHA256).Hash
    # stable path for program_full.tcl (the timestamped dir is provenance only)
    Copy-Item -LiteralPath $bitstream -Destination ([System.IO.Path]::Combine($project, 'build', 'pds-latest.sbit')) -Force
    $manifest = [ordered]@{
        Schema = 1; BuildDirectory = $buildRoot; Bitstream = $bitstream; BitstreamSha256 = $sbitHash
        FirmwareSha256 = $fwHash; Device = 'PG2L100H-6IFBG676'; ClockHz = 27000000
        UartBaud = $UartBaud; EnableM = $EnableM; GeneratedUtc = [datetime]::UtcNow.ToString('o')
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($buildRoot, 'manifest.json')) -Encoding utf8
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', 'pds-latest.json')) -Encoding utf8
    Write-Output "Bitstream: $bitstream"
    Write-Output "SHA-256: $sbitHash"
} catch {
    Write-Error $_
    exit 1
}
