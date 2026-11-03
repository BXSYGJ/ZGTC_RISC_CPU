[CmdletBinding()]
param(
    [ValidateSet('full', 'ddr3_diag', 'ui_demo', 'conv1_test', 'mel_test', 'core_only', 'rv_core', 'pcm1808_diag')]
    [string]$BuildSet = 'full',

    [string]$TopModule = '',

    [ValidateSet('', 'compile', 'synthesize', 'dev_map')]
    [string]$StopAfter = '',

    [switch]$DryRun
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

function Expand-BuildSetFiles {
    param(
        [string]$Root,
        [string[]]$Patterns
    )
    $ordered = New-Object System.Collections.Generic.List[string]
    $comparison = [System.StringComparer]::OrdinalIgnoreCase
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' -ArgumentList $comparison
    foreach ($pattern in $Patterns) {
        if ([string]::IsNullOrWhiteSpace($pattern)) { continue }
        $relative = $pattern.Replace('/', '\')
        $expanded = [System.IO.Path]::Combine($Root, $relative)
        if ($pattern.Contains('*') -or $pattern.Contains('?')) {
            $hits = @(Get-ChildItem -Path $expanded -File -ErrorAction SilentlyContinue | Sort-Object FullName)
            foreach ($hit in $hits) {
                if ($seen.Add($hit.FullName)) { [void]$ordered.Add($hit.FullName) }
            }
        } else {
            $fullPath = [System.IO.Path]::GetFullPath($expanded)
            if ($seen.Add($fullPath)) { [void]$ordered.Add($fullPath) }
        }
    }
    return ,$ordered.ToArray()
}

function ConvertTo-TclLines {
    param(
        [string[]]$Files,
        [string]$Verb
    )
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($file in $Files) {
        [void]$lines.Add($Verb + ' "' + $file.Replace('\', '/') + '"')
    }
    return (($lines.ToArray()) -join "`n")
}

function Get-SourceDigest {
    param([string]$Path)
    $hash = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        return ([System.BitConverter]::ToString($hash.ComputeHash($stream)) -replace '-', '')
    } finally {
        $stream.Dispose()
        $hash.Dispose()
    }
}

try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))

    $setsPath = [System.IO.Path]::Combine($PSScriptRoot, 'build_sets.json')
    if (-not (Test-Path -LiteralPath $setsPath -PathType Leaf)) { throw "Build set manifest not found: $setsPath" }
    $setsDoc = [System.IO.File]::ReadAllText($setsPath) | ConvertFrom-Json
    if ([int]$setsDoc.schema -ne 1) { throw "Unsupported build_sets.json schema $($setsDoc.schema); expected 1." }
    if ($null -eq $setsDoc.sets) { throw "build_sets.json has no 'sets' object." }
    $setProperty = $setsDoc.sets.PSObject.Properties[$BuildSet]
    if ($null -eq $setProperty) {
        $knownSets = @($setsDoc.sets.PSObject.Properties.Name)
        throw "Unknown build set '$BuildSet'; build_sets.json defines: $($knownSets -join ', ')."
    }
    $setDef = $setProperty.Value
    $setTopModule = [string]$setDef.top_module
    if ([string]::IsNullOrWhiteSpace($setTopModule)) { throw "Build set '$BuildSet' has no top_module." }
    if ([string]::IsNullOrWhiteSpace($TopModule)) {
        $topModule = $setTopModule
    } elseif ($TopModule -ne $setTopModule) {
        throw "-TopModule '$TopModule' conflicts with build set '$BuildSet' (top_module '$setTopModule')."
    } else {
        $topModule = $TopModule
    }
    $projectName = $topModule + '_pds'

    $designFiles = Expand-BuildSetFiles -Root $project -Patterns @($setDef.sources)
    $ipFiles = Expand-BuildSetFiles -Root $project -Patterns @($setDef.ip_cores)
    $constraintFiles = Expand-BuildSetFiles -Root $project -Patterns @($setDef.constraints)
    $hexDirs = @($setDef.hex_dirs)
    if ($designFiles.Count -eq 0) {
        throw "Build set '$BuildSet' expands to zero design files; check its 'sources' globs in build_sets.json."
    }

    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $buildRoot = [System.IO.Path]::Combine($project, 'build', 'pds', $runName)
    [void](New-Item -ItemType Directory -Path $buildRoot -Force)

    $tclTemplatePath = [System.IO.Path]::Combine($PSScriptRoot, 'build_full.tcl')
    if (-not (Test-Path -LiteralPath $tclTemplatePath -PathType Leaf)) { throw "PDS build template not found: $tclTemplatePath" }
    $tclTemplate = [System.IO.File]::ReadAllText($tclTemplatePath)

    $hexLines = New-Object System.Collections.Generic.List[string]
    $hexSourceFiles = New-Object System.Collections.Generic.List[string]
    $hexCount = 0
    foreach ($hexDir in $hexDirs) {
        $hexRelative = ([string]$hexDir).Replace('/', '\')
        $hexSourceDir = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($project, $hexRelative))
        $hexTargetDir = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($buildRoot, $hexRelative))
        [void]$hexLines.Add('file mkdir "' + $hexTargetDir.Replace('\', '/') + '"')
        $hexTargetTcl = $hexTargetDir.Replace('\', '/')
        $hexHits = @(Get-ChildItem -Path ([System.IO.Path]::Combine($hexSourceDir, '*.hex')) -File -ErrorAction SilentlyContinue | Sort-Object FullName)
        foreach ($hexFile in $hexHits) {
            [void]$hexSourceFiles.Add($hexFile.FullName)
            [void]$hexLines.Add('file copy -force "' + $hexFile.FullName.Replace('\', '/') + '" "' + $hexTargetTcl + '"')
            $hexCount = $hexCount + 1
        }
    }

    $tokenValues = [ordered]@{
        '__DESIGN_FILES__'     = (ConvertTo-TclLines -Files $designFiles -Verb 'add_design')
        '__IP_FILES__'         = (ConvertTo-TclLines -Files $ipFiles -Verb 'add_design')
        '__CONSTRAINT_FILES__' = (ConvertTo-TclLines -Files $constraintFiles -Verb 'add_constraint')
        '__HEX_COPY_BLOCK__'   = (($hexLines.ToArray()) -join "`n")
        '__PROJECT_ROOT__'     = $project.Replace('\', '/')
        '__BUILD_ROOT__'       = $buildRoot.Replace('\', '/')
        '__TOP_MODULE__'       = $topModule
        '__PROJECT_NAME__'     = $projectName
    }
    $tcl = $tclTemplate
    foreach ($token in $tokenValues.Keys) {
        if (-not $tclTemplate.Contains($token)) { throw "build_full.tcl is missing the $token token." }
        $tcl = $tcl.Replace($token, $tokenValues[$token])
    }
    if ($tcl.Contains('__')) { throw 'build.tcl still contains an unexpanded __TOKEN__ placeholder.' }

    if ($StopAfter -ne '') {
        $nextStage = @{ compile = 'synthesize'; synthesize = 'dev_map'; dev_map = 'pnr' }[$StopAfter]
        $lines = $tcl -split "`r?`n"
        $idx = -1
        for ($li = 0; $li -lt $lines.Count; $li++) {
            if ($lines[$li].Trim() -match ('^' + [regex]::Escape($nextStage) + '(\s|$)')) { $idx = $li; break }
        }
        if ($idx -lt 0) { throw "StopAfter: stage '$nextStage' not found in build.tcl" }
        $head = @()
        if ($idx -gt 0) { $head = $lines[0..($idx - 1)] }
        $tail = @()
        if ($idx -lt $lines.Count) { $tail = $lines[$idx..($lines.Count - 1)] }
        $tcl = (@($head) + @('if {[llength [info commands open_project]]} {exit}') + @($tail)) -join "`n"
        Write-Output ("StopAfter={0}: build.tcl will exit before '{1}'." -f $StopAfter, $nextStage)
    }

    $scriptPath = [System.IO.Path]::Combine($buildRoot, 'build.tcl')
    [System.IO.File]::WriteAllText($scriptPath, $tcl, [System.Text.UTF8Encoding]::new($false))

    if ($DryRun) {
        Write-Output ('DRYRUN top={0} set={1} design={2} ip={3} constraint={4} hex={5}' -f $topModule, $BuildSet, $designFiles.Count, $ipFiles.Count, $constraintFiles.Count, $hexCount)
        Write-Output ('DRYRUN build.tcl: ' + $scriptPath)
        Write-Output ('DRYRUN project_name: ' + $projectName)
        exit 0
    }

    if (@(Get-Process -Name pds_shell -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'A pds_shell process already exists; only one PDS build is allowed.'
    }

    $sourceRecords = @()
    $sourcePaths = @($designFiles) + @($ipFiles) + @($constraintFiles) + @($hexSourceFiles.ToArray()) + @($setsPath, $tclTemplatePath, $PSCommandPath)
    foreach ($sourcePath in @($sourcePaths | Sort-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw "Build input not found: $sourcePath" }
        $sourceRecords += [ordered]@{
            Path = $sourcePath
            Sha256 = (Get-SourceDigest -Path $sourcePath)
            LastWriteUtc = (Get-Item -LiteralPath $sourcePath).LastWriteTimeUtc.ToString('o')
        }
    }
    $sourceManifestPath = [System.IO.Path]::Combine($buildRoot, 'source-manifest.json')
    $sourceManifest = [ordered]@{ Schema = 1; BuildSet = $BuildSet; CapturedUtc = [datetime]::UtcNow.ToString('o'); Files = $sourceRecords }
    [System.IO.File]::WriteAllText($sourceManifestPath, ($sourceManifest | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))

    $pdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'Process')
    if ([string]::IsNullOrWhiteSpace($pdsRoot)) { $pdsRoot = 'H:\GG\pango\PDS_2022.2-SP6.4' }
    $pdsShell = [System.IO.Path]::Combine($pdsRoot, 'bin', 'pds_shell.exe')
    if (-not (Test-Path -LiteralPath $pdsShell -PathType Leaf)) { throw "PDS shell not found: $pdsShell" }

    $licenseFile = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($licenseFile)) { $licenseFile = 'E:\License\pango\new_pds_F4A80DA47D72.lic' }
    if (-not (Test-Path -LiteralPath $licenseFile -PathType Leaf)) { throw "PANGO license file not found: $licenseFile" }
    $env:PANGO_LICENSE_FILE = $licenseFile

    $stdout = [System.IO.Path]::Combine($buildRoot, 'pds.stdout.log')
    $stderr = [System.IO.Path]::Combine($buildRoot, 'pds.stderr.log')
    $arguments = @('-file', ('"' + $scriptPath + '"'), '-work_dir', ('"' + $buildRoot + '"'), '-project_name', $projectName)
    if (@(Get-Process -Name pds_shell -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'A pds_shell process appeared before launch; only one PDS build is allowed.'
    }
    Write-Output "PDS build directory: $buildRoot"
    Write-Output "PDS source manifest: $sourceManifestPath"
    $started = [datetime]::UtcNow
    $process = Start-Process -FilePath $pdsShell -ArgumentList $arguments -PassThru -WindowStyle Hidden -Wait -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-Output "PDS PID: $($process.Id)"
    Write-Output "PDS build directory: $buildRoot"
    $outputText = [System.IO.File]::ReadAllText($stdout)
    if ((Test-Path -LiteralPath $stderr -PathType Leaf)) { $outputText = $outputText + [System.IO.File]::ReadAllText($stderr) }
    Write-Output "PDS ExitCode: $($process.ExitCode)"

    $changedSources = @()
    foreach ($record in $sourceRecords) {
        if (-not (Test-Path -LiteralPath $record.Path -PathType Leaf)) {
            $changedSources += $record.Path
        } elseif ((Get-SourceDigest -Path $record.Path) -ne $record.Sha256) {
            $changedSources += $record.Path
        }
    }
    $sourceValidation = [ordered]@{ CheckedUtc = [datetime]::UtcNow.ToString('o'); Unchanged = ($changedSources.Count -eq 0); ChangedFiles = $changedSources }
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($buildRoot, 'source-validation.json'), ($sourceValidation | ConvertTo-Json -Depth 4), [System.Text.UTF8Encoding]::new($false))
    if ($changedSources.Count -gt 0) {
        throw ("Build inputs changed during PDS; refusing publication: " + ($changedSources -join ', '))
    }

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

    $stages = @('compile', 'synthesize', 'dev_map', 'pnr', 'report_timing', 'gen_bit_stream')
    $stageStatus = @()
    foreach ($stage in $stages) {
        $ok = [regex]::IsMatch($outputText, ('Executing\s*:\s*' + [regex]::Escape($stage) + '\b[^\r\n]*successfully\.'))
        if ($ok) { $status = 'OK' } else { $status = 'FAIL' }
        $stageStatus += [ordered]@{ Stage = $stage; Status = $status }
    }
    Write-Output '--- stage status ---'
    foreach ($s in $stageStatus) { Write-Output ("{0}: {1}" -f $s.Stage, $s.Status) }

    $bitstream = [System.IO.Path]::Combine($buildRoot, 'generate_bitstream', ($topModule + '.sbit'))
    $sbitHash = ''
    if ($StopAfter -eq '') {
        if (-not (Test-Path -LiteralPath $bitstream -PathType Leaf)) { throw "PDS did not produce the expected bitstream: $bitstream" }
        if ((Get-Item -LiteralPath $bitstream).LastWriteTimeUtc -lt $started.AddSeconds(-1)) { throw 'Bitstream is stale (older than this run).' }

        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        $shaStream = [System.IO.File]::OpenRead($bitstream)
        try {
            $sbitHash = ([System.BitConverter]::ToString($sha256.ComputeHash($shaStream)) -replace '-', '')
        } finally {
            $shaStream.Dispose()
            $sha256.Dispose()
        }
    } else {
        Write-Output ("StopAfter={0}: no bitstream expected." -f $StopAfter)
    }

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

    $wns = ''
    $whs = ''
    $rtrPath = [System.IO.Path]::Combine($buildRoot, 'report_timing', ($topModule + '.rtr'))
    if (Test-Path -LiteralPath $rtrPath -PathType Leaf) {
        $rtr = [System.IO.File]::ReadAllText($rtrPath)
        $setupIdx = $rtr.IndexOf('Setup Summary(Slow Corner):')
        $holdIdx = $rtr.IndexOf('Hold Summary(Slow Corner):')
        if ($setupIdx -ge 0 -and $holdIdx -gt $setupIdx) {
            $setupBlock = $rtr.Substring($setupIdx, $holdIdx - $setupIdx)
            $matches = [regex]::Matches($setupBlock, '(?m)^.*?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s*$')
            if ($matches.Count -gt 0) {
                $wns = ($matches | ForEach-Object { [double]::Parse($_.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) } | Measure-Object -Minimum).Minimum
            }
        }
        if ($holdIdx -ge 0) {
            $recoveryIdx = $rtr.IndexOf('Recovery Summary(Slow Corner):')
            if ($recoveryIdx -gt $holdIdx) {
                $holdBlock = $rtr.Substring($holdIdx, $recoveryIdx - $holdIdx)
            } else {
                $holdBlock = $rtr.Substring($holdIdx)
            }
            $matches = [regex]::Matches($holdBlock, '(?m)^.*?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s*$')
            if ($matches.Count -gt 0) {
                $whs = ($matches | ForEach-Object { [double]::Parse($_.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) } | Measure-Object -Minimum).Minimum
            }
        }
    }
    if ($wns -ne '') { Write-Output "WNS (setup, slow corner): $wns ns" } else { Write-Output 'WNS (setup, slow corner): not found' }
    if ($whs -ne '') { Write-Output "WHS (hold, slow corner): $whs ns" } else { Write-Output 'WHS (hold, slow corner): not found' }

    if ($BuildSet -eq 'full') { $latestBase = 'instrec-latest' } else { $latestBase = $topModule + '-latest' }
    $reportsDir = [System.IO.Path]::Combine($project, 'reports')
    [void](New-Item -ItemType Directory -Path $reportsDir -Force)
    $archivedStdout = [System.IO.Path]::Combine($reportsDir, ('build_' + $runName + '.pds.stdout.log'))
    Copy-Item -LiteralPath $stdout -Destination $archivedStdout -Force
    if ((Test-Path -LiteralPath $stderr -PathType Leaf)) {
        Copy-Item -LiteralPath $stderr -Destination ([System.IO.Path]::Combine($reportsDir, ('build_' + $runName + '.pds.stderr.log'))) -Force
    }
    if ($StopAfter -eq '') {
        Copy-Item -LiteralPath $bitstream -Destination ([System.IO.Path]::Combine($project, 'build', ($latestBase + '.sbit'))) -Force
    }

    $manifest = [ordered]@{
        Schema = 1
        BuildSet = $BuildSet
        RunName = $runName
        StopAfter = $StopAfter
        SourceManifest = $sourceManifestPath
        SourcesUnchanged = $true
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
    if ($StopAfter -eq '') {
        [System.IO.File]::WriteAllText([System.IO.Path]::Combine($project, 'build', ($latestBase + '.json')), $manifestJson, [System.Text.UTF8Encoding]::new($false))
    }

    Write-Output "Bitstream: $bitstream"
    Write-Output "SHA-256: $sbitHash"
    Write-Output "Archived log: $archivedStdout"
    Write-Output '--- PDS output tail ---'
    $outputText -split "`r?`n" | Where-Object { $_ -ne '' } | Select-Object -Last 12 | ForEach-Object { Write-Output $_ }
} catch {
    Write-Error $_
    exit 1
}
