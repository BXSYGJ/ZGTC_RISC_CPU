# One-button InstRec-FPGA PDS build: expand build_full.tcl tokens, run the
# six-stage batch flow (compile -> synthesize -> dev_map -> pnr ->
# report_timing -> gen_bit_stream) through pds_shell.exe, scan the logs for
# tool errors, verify the sbit, and archive logs to reports/ (REQ-BLD-001).
#
# Build sets (C-BUILD-TOKENS@1): the design sources, IP cores, constraints and
# $readmemh table directories are read from scripts/build_sets.json, so one
# six-stage TCL drives every build line:
#   full       instrec_top      the whole SoC (~1.5 h place and route)
#   ddr3_diag  top_ddr3_diag    DDR3 bring-up scope only (minutes)
#   ui_demo    top_ui_demo      HDMI + UI scope only (minutes)
#   conv1_test top_npu_conv1_test  conv1 layer, BRAM weights (minutes)
#   mel_test   top_mel_test     mel engine, fake PCM source (minutes)
#   core_only  top_core_only    DDR3 + NPU + Mel + control, no video half
#                               (the LUT-reduced full top, T36)
#   rv_core    top_rv_core      core_only plus RV32I control firmware/CPU
#
# Parameters:
#   -BuildSet <full|ddr3_diag|ui_demo|conv1_test|mel_test|core_only|rv_core>
#       build set to run (default: full).
#   -TopModule <name>  explicit override of the set's top_module.  A mismatch
#       throws, because the artifact name is derived from the top module and a
#       silent mismatch would publish a bitstream under the wrong name.
#   -DryRun  read the set, expand the globs, substitute the eight tokens and
#       write build/pds/<run>/build.tcl, then print a one-line summary and
#       exit 0.  pds_shell.exe is NEVER started.  This is how the pipeline is
#       verified without spending the single build slot.
#
# Artifact names: "full" keeps the historical build/instrec-latest.sbit and
# build/instrec-latest.json (backward compatible); every other set writes
# build/<TopModule>-latest.sbit / build/<TopModule>-latest.json so the three
# build lines coexist under build/.
#
# PowerShell 5.1 compatibility rules (hard constraints):
#   - Start-Process is ALWAYS called with -Wait: without it $process.ExitCode
#     stays $null on PS5.1 and the failure check misfires.
#   - All generated text files are written via [System.IO.File]::WriteAllText
#     with an explicit BOM-less UTF8 encoding; "Set-Content -Encoding UTF8"
#     is avoided because it emits a BOM on PS5.1.
#   - No PS7-only operators (ternary / null-coalescing / chain operators).
[CmdletBinding()]
param(
    [ValidateSet('full', 'ddr3_diag', 'ui_demo', 'conv1_test', 'mel_test', 'core_only', 'rv_core', 'pcm1808_diag', 'emergency_demo', 'i2s_capture')]
    [string]$BuildSet = 'full',

    [string]$TopModule = '',

    # Stop after one stage and skip the bitstream checks.  Used for the
    # resource gate (synthesize): the LUT total decides whether a two-hour
    # place-and-route is worth starting, and synth+dev_map cost ~20 minutes.
    [ValidateSet('', 'compile', 'synthesize', 'dev_map')]
    [string]$StopAfter = '',

    # Placement seed base handed to 'pnr -gplace_seed'.  The template's default
    # (7) is the layout every archived build used; a different base asks PDS for
    # a different set of -parallel candidates, which is the only lever that
    # moves WNS on this design (the failing paths are placement-bound, not
    # logic-depth-bound).  Recorded in build/instrec-latest.json.
    [int]$PlacementSeed = 7,

    [switch]$DryRun
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

# Expand one build-set file list into absolute paths.  Entries containing a
# wildcard are globbed (a missing directory expands to nothing, so a milestone
# tree that does not have every directory yet still produces a valid list);
# entries without a wildcard are kept verbatim even when the file does not
# exist yet, because the build sets reference assets other tasks deliver in
# parallel and the -DryRun check only validates the generated path strings.
# Order is preserved (constraint order is semantic) and duplicates are dropped.
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

# Join a path list into "add_design "<abs>"" / "add_constraint "<abs>"" TCL
# lines.  Paths use forward slashes so the generated TCL never needs escaping.
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

    # 0) resolve the build set before creating any directory, so a bad set name
    #    or a conflicting -TopModule leaves no empty build/ run behind.
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

    # 0b) expand the design / IP / constraint lists of the set
    $designFiles = Expand-BuildSetFiles -Root $project -Patterns @($setDef.sources)
    $ipFiles = Expand-BuildSetFiles -Root $project -Patterns @($setDef.ip_cores)
    $constraintFiles = Expand-BuildSetFiles -Root $project -Patterns @($setDef.constraints)
    $hexDirs = @($setDef.hex_dirs)
    if ($designFiles.Count -eq 0) {
        throw "Build set '$BuildSet' expands to zero design files; check its 'sources' globs in build_sets.json."
    }

    # 1) timestamped build directory (provenance; build/ is git-ignored)
    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $buildRoot = [System.IO.Path]::Combine($project, 'build', 'pds', $runName)
    [void](New-Item -ItemType Directory -Path $buildRoot -Force)

    # 2) expand the PDS TCL template (eight tokens, C-BUILD-TOKENS@1)
    $tclTemplatePath = [System.IO.Path]::Combine($PSScriptRoot, 'build_full.tcl')
    if (-not (Test-Path -LiteralPath $tclTemplatePath -PathType Leaf)) { throw "PDS build template not found: $tclTemplatePath" }
    $tclTemplate = [System.IO.File]::ReadAllText($tclTemplatePath)

    # $readmemh tables: copy every table of each hex_dir into <build>/<hex_dir>
    # so the work_dir-relative "src/mel/..." / "src/ui/..." prefixes resolve.
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

    # Block tokens are substituted before the scalar ones so that a block which
    # happens to reference __BUILD_ROOT__ / __PROJECT_ROOT__ is expanded too.
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

    # Placement seed override (see the -PlacementSeed comment): only the pnr
    # line carries it, and the template default stays 7 for every archived run.
    if ($PlacementSeed -ne 7) {
        $tcl = [regex]::Replace($tcl, '-gplace_seed\s+\d+', "-gplace_seed $PlacementSeed")
        Write-Output ("PlacementSeed={0} (template default 7 overridden)." -f $PlacementSeed)
    }

    # -StopAfter: insert an 'exit' line in front of the next stage instead of
    # editing build_full.tcl (the template stays the single six-stage source).
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

    # 2b) -DryRun: the tokenisation is proven by build.tcl alone, so stop here
    #     and never touch pds_shell.exe, the license or the JTAG chain.
    if ($DryRun) {
        Write-Output ('DRYRUN top={0} set={1} design={2} ip={3} constraint={4} hex={5}' -f $topModule, $BuildSet, $designFiles.Count, $ipFiles.Count, $constraintFiles.Count, $hexCount)
        Write-Output ('DRYRUN build.tcl: ' + $scriptPath)
        Write-Output ('DRYRUN project_name: ' + $projectName)
        exit 0
    }

    if (@(Get-Process -Name pds_shell -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'A pds_shell process already exists; only one PDS build is allowed.'
    }

    # Record inputs before PDS reads live source paths. A later change makes
    # this run unsuitable for publication even if PDS produces a bitstream.
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
    $sbitHash = ''
    if ($StopAfter -eq '') {
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
    } else {
        Write-Output ("StopAfter={0}: no bitstream expected." -f $StopAfter)
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
    #    so anchor on the line ending and take the worst clock row.
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

    # 10) archive logs to reports/ (timestamped) + stable bitstream copy.
    #     "full" keeps the historical instrec-latest.* names; the other sets
    #     write <TopModule>-latest.* so the three lines coexist in build/.
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

    # 11) manifest (build provenance, REQ-BLD-001)
    $manifest = [ordered]@{
        Schema = 1
        BuildSet = $BuildSet
        RunName = $runName
        StopAfter = $StopAfter
        PlacementSeed = $PlacementSeed
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
