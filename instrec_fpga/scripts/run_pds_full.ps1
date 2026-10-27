# One-button InstRec-FPGA PDS build: expand build_full.tcl tokens, run the
# six-stage batch flow (compile -> synthesize -> dev_map -> pnr ->
# report_timing -> gen_bit_stream) through pds_shell.exe, scan the logs for
# tool errors, verify the sbit, and archive logs to reports/ (REQ-BLD-001).
#
# PowerShell 5.1 compatibility rules (hard constraints):
#   - Start-Process is ALWAYS called with -Wait: without it $process.ExitCode
#     stays $null on PS5.1 and the failure check misfires.
#   - All generated text files are written via [System.IO.File]::WriteAllText
#     with an explicit BOM-less UTF8 encoding; "Set-Content -Encoding UTF8"
#     is avoided because it emits a BOM on PS5.1.
#   - No PS7-only operators (ternary / null-coalescing / chain operators).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $topModule = 'instrec_top'
    $projectName = 'instrec_fpga'

    # 1) timestamped build directory (provenance; build/ is git-ignored)
    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $buildRoot = [System.IO.Path]::Combine($project, 'build', 'pds', $runName)
    [void](New-Item -ItemType Directory -Path $buildRoot -Force)

    # 2) expand the PDS TCL template
    $tclTemplatePath = [System.IO.Path]::Combine($PSScriptRoot, 'build_full.tcl')
    if (-not (Test-Path -LiteralPath $tclTemplatePath -PathType Leaf)) { throw "PDS build template not found: $tclTemplatePath" }
    $tclTemplate = [System.IO.File]::ReadAllText($tclTemplatePath)
    if (-not $tclTemplate.Contains('__PROJECT_ROOT__')) { throw 'build_full.tcl is missing the __PROJECT_ROOT__ token.' }
    $tcl = $tclTemplate.Replace('__PROJECT_ROOT__', $project.Replace('\', '/')).Replace('__BUILD_ROOT__', $buildRoot.Replace('\', '/'))
    $scriptPath = [System.IO.Path]::Combine($buildRoot, 'build.tcl')
    [System.IO.File]::WriteAllText($scriptPath, $tcl, [System.Text.UTF8Encoding]::new($false))

    # 3) locate PDS and the license, both hard-checked before the run
    $pdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'Process')
    if ([string]::IsNullOrWhiteSpace($pdsRoot)) { $pdsRoot = 'H:\GG\pango\PDS_2022.2-SP6.4' }
    $pdsShell = [System.IO.Path]::Combine($pdsRoot, 'bin', 'pds_shell.exe')
    if (-not (Test-Path -LiteralPath $pdsShell -PathType Leaf)) { throw "PDS shell not found: $pdsShell" }

    $licenseFile = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($licenseFile)) { $licenseFile = 'E:\License\pango\new_pds_F4A80DA47D72.lic' }
    if (-not (Test-Path -LiteralPath $licenseFile -PathType Leaf)) { throw "PANGO license file not found: $licenseFile" }
    $env:PANGO_LICENSE_FILE = $licenseFile

    # 4) run the PDS batch flow (-Wait is mandatory so ExitCode is reliable)
    $stdout = [System.IO.Path]::Combine($buildRoot, 'pds.stdout.log')
    $stderr = [System.IO.Path]::Combine($buildRoot, 'pds.stderr.log')
    $arguments = @('-file', ('"' + $scriptPath + '"'), '-work_dir', ('"' + $buildRoot + '"'), '-project_name', $projectName)
    $started = [datetime]::UtcNow
    $process = Start-Process -FilePath $pdsShell -ArgumentList $arguments -PassThru -WindowStyle Hidden -Wait -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-Output "PDS PID: $($process.Id)"
    Write-Output "PDS build directory: $buildRoot"
    $outputText = [System.IO.File]::ReadAllText($stdout)
    if ((Test-Path -LiteralPath $stderr -PathType Leaf)) { $outputText = $outputText + [System.IO.File]::ReadAllText($stderr) }
    Write-Output "PDS ExitCode: $($process.ExitCode)"

    # 5) scan for tool errors; "SCBV has not been set" / Bitstream-2001 is a
    #    known benign notice on boards without PCB SCBV data, not an error.
    $errorLines = @()
    foreach ($line in ($outputText -split "`r?`n")) {
        if ($line -match '^E:') {
            if ($line -match 'SCBV has not been set' -or $line -match 'Bitstream-2001') { continue }
            $errorLines += $line
        }
    }
    if ($process.ExitCode -ne 0) { throw "PDS exited with code $($process.ExitCode); inspect $stdout" }
    if ($errorLines.Count -gt 0) {
        $errorLines | Select-Object -First 10 | ForEach-Object { Write-Output $_ }
        throw 'PDS reported tool errors; inspect the build logs.'
    }

    # 6) per-stage success check (six stages of design doc section 12.2).
    #    The completion banner repeats the full command line ("Executing :
    #    compile -system_verilog -top_module instrec_top successfully."),
    #    so match the stage keyword followed by anything up to successfully.
    $stages = @('compile', 'synthesize', 'dev_map', 'pnr', 'report_timing', 'gen_bit_stream')
    $stageStatus = @()
    foreach ($stage in $stages) {
        $ok = [regex]::IsMatch($outputText, ('Executing\s*:\s*' + [regex]::Escape($stage) + '\b[^\r\n]*successfully\.'))
        if ($ok) { $status = 'OK' } else { $status = 'FAIL' }
        $stageStatus += [ordered]@{ Stage = $stage; Status = $status }
    }
    Write-Output '--- stage status ---'
    foreach ($s in $stageStatus) { Write-Output ("{0}: {1}" -f $s.Stage, $s.Status) }

    # 7) verify the bitstream (fresh file + sha256, REQ-BLD-001)
    $bitstream = [System.IO.Path]::Combine($buildRoot, 'generate_bitstream', ($topModule + '.sbit'))
    if (-not (Test-Path -LiteralPath $bitstream -PathType Leaf)) { throw "PDS did not produce the expected bitstream: $bitstream" }
    if ((Get-Item -LiteralPath $bitstream).LastWriteTimeUtc -lt $started.AddSeconds(-1)) { throw 'Bitstream is stale (older than this run).' }
    # Get-FileHash is not available in every PS 5.1 installation; use .NET.
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $shaStream = [System.IO.File]::OpenRead($bitstream)
    try {
        $sbitHash = ([System.BitConverter]::ToString($sha256.ComputeHash($shaStream)) -replace '-', '')
    } finally {
        $shaStream.Dispose()
        $sha256.Dispose()
    }

    # 8) extract the post-PnR device utilization summary from the log.
    #    The table splits FF/LUT rows per logic-array segment (CLMA/CLMS),
    #    so FF/LUT are summed to the device totals; other key resources are
    #    reported once (first occurrence wins).
    $lutUsed = 0; $lutAvail = 0; $ffUsed = 0; $ffAvail = 0
    $utilSummary = @()
    $seenNames = @()
    $interesting = @('DRM', 'Distributed RAM', 'GPLL', 'PPLL', 'APM', 'IO', 'BKCL', 'HCKB', 'CCS', 'USCM', 'SCANCHAIN')
    $lastUtil = $outputText.LastIndexOf('Device Utilization Summary')
    if ($lastUtil -ge 0) {
        $utilBlock = $outputText.Substring($lastUtil)
        foreach ($m in [regex]::Matches($utilBlock, '(?m)^\|\s*([A-Za-z_ ]+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)')) {
            $name = ($m.Groups[1].Value.Trim() -replace '^Use of ', '')
            $used = [int]$m.Groups[2].Value
            $avail = [int]$m.Groups[3].Value
            if ($name -eq 'FF') {
                $ffUsed += $used; $ffAvail += $avail
            } elseif ($name -eq 'LUT') {
                $lutUsed += $used; $lutAvail += $avail
            } elseif (($interesting -contains $name) -and ($seenNames -notcontains $name)) {
                $seenNames += $name
                $utilSummary += ('{0}: {1}/{2} ({3}%)' -f $name, $used, $avail, $m.Groups[4].Value)
            }
        }
        if ($ffAvail -gt 0) { $utilSummary = @(('FF total: {0}/{1} ({2}%)' -f $ffUsed, $ffAvail, [math]::Round(100.0 * $ffUsed / $ffAvail, 0))) + $utilSummary }
        if ($lutAvail -gt 0) { $utilSummary = @(('LUT total: {0}/{1} ({2}%)' -f $lutUsed, $lutAvail, [math]::Round(100.0 * $lutUsed / $lutAvail, 0))) + $utilSummary }
    }
    Write-Output '--- device utilization (post-PnR) ---'
    if ($utilSummary.Count -gt 0) { $utilSummary | ForEach-Object { Write-Output $_ } } else { Write-Output '(utilization summary not found in log)' }

    # 9) extract WNS/WHS from the post-PnR timing report (.rtr). The setup
    #    table line ends with four numbers (WNS TNS failing total); the row
    #    may carry the clock names on the same line or on preceding lines,
    #    so anchor on the line ending.
    $wns = ''
    $whs = ''
    $rtrPath = [System.IO.Path]::Combine($buildRoot, 'report_timing', ($topModule + '.rtr'))
    if (Test-Path -LiteralPath $rtrPath -PathType Leaf) {
        $rtr = [System.IO.File]::ReadAllText($rtrPath)
        $setupIdx = $rtr.IndexOf('Setup Summary(Slow Corner):')
        $holdIdx = $rtr.IndexOf('Hold Summary(Slow Corner):')
        if ($setupIdx -ge 0 -and $holdIdx -gt $setupIdx) {
            $setupBlock = $rtr.Substring($setupIdx, $holdIdx - $setupIdx)
            $m = [regex]::Match($setupBlock, '(?m)^.*?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s*$')
            if ($m.Success) { $wns = $m.Groups[1].Value }
        }
        if ($holdIdx -ge 0) {
            $recoveryIdx = $rtr.IndexOf('Recovery Summary(Slow Corner):')
            if ($recoveryIdx -gt $holdIdx) {
                $holdBlock = $rtr.Substring($holdIdx, $recoveryIdx - $holdIdx)
            } else {
                $holdBlock = $rtr.Substring($holdIdx)
            }
            $m = [regex]::Match($holdBlock, '(?m)^.*?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s*$')
            if ($m.Success) { $whs = $m.Groups[1].Value }
        }
    }
    if ($wns -ne '') { Write-Output "WNS (setup, slow corner): $wns ns" } else { Write-Output 'WNS (setup, slow corner): not found' }
    if ($whs -ne '') { Write-Output "WHS (hold, slow corner): $whs ns" } else { Write-Output 'WHS (hold, slow corner): not found' }

    # 10) archive logs to reports/ (timestamped) + stable bitstream copy
    $reportsDir = [System.IO.Path]::Combine($project, 'reports')
    [void](New-Item -ItemType Directory -Path $reportsDir -Force)
    $archivedStdout = [System.IO.Path]::Combine($reportsDir, ('build_' + $runName + '.pds.stdout.log'))
    Copy-Item -LiteralPath $stdout -Destination $archivedStdout -Force
    if ((Test-Path -LiteralPath $stderr -PathType Leaf)) {
        Copy-Item -LiteralPath $stderr -Destination ([System.IO.Path]::Combine($reportsDir, ('build_' + $runName + '.pds.stderr.log'))) -Force
    }
    Copy-Item -LiteralPath $bitstream -Destination ([System.IO.Path]::Combine($project, 'build', 'instrec-latest.sbit')) -Force

    # 11) manifest (build provenance, REQ-BLD-001)
    $manifest = [ordered]@{
        Schema = 1
        RunName = $runName
        BuildDirectory = $buildRoot
        Device = 'PG2L100H-6IFBG676'
        TopModule = $topModule
        ProjectName = $projectName
        PdsRoot = $pdsRoot
        LicenseFile = $licenseFile
        StageStatus = $stageStatus
        Utilization = $utilSummary
        Wns = $wns
        Whs = $whs
        Bitstream = $bitstream
        BitstreamSha256 = $sbitHash
        GeneratedUtc = [datetime]::UtcNow.ToString('o')
    }
    $manifestJson = $manifest | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($buildRoot, 'manifest.json'), $manifestJson, [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($project, 'build', 'instrec-latest.json'), $manifestJson, [System.Text.UTF8Encoding]::new($false))

    Write-Output "Bitstream: $bitstream"
    Write-Output "SHA-256: $sbitHash"
    Write-Output "Archived log: $archivedStdout"
    Write-Output '--- PDS output tail ---'
    $outputText -split "`r?`n" | Where-Object { $_ -ne '' } | Select-Object -Last 12 | ForEach-Object { Write-Output $_ }
} catch {
    Write-Error $_
    exit 1
}