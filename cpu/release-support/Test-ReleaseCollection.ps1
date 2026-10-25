[CmdletBinding()]
param(
    [string]$CpuRoot=[IO.Path]::Combine($PSScriptRoot,'..'),
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$OutputDirectory
)
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$OutputEncoding=[Text.UTF8Encoding]::new($true)
$ErrorActionPreference='Stop'
try {
    $cpu=[IO.Path]::GetFullPath($CpuRoot)
    $output=[IO.Path]::GetFullPath($OutputDirectory)
    if($output -eq $cpu -or $output.StartsWith($cpu+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Write verification outputs outside the frozen CPU tree.'
    }
    if(Test-Path -LiteralPath $output){throw 'Use a new output directory.'}
    New-Item -ItemType Directory -Path $output|Out-Null
    $scripts=[IO.Path]::Combine($PSScriptRoot,'scripts')
    & ([IO.Path]::Combine($scripts,'Verify-Package.ps1')) -PackageRoot $cpu
    if($LASTEXITCODE -ne 0){throw 'SHA-256 collection manifest did not pass.'}
    . ([IO.Path]::Combine($scripts,'Common.ps1'))
    $summary=[Collections.Generic.List[object]]::new()
    $sourceChecks=0
    $captures=0
    $reports=0
    function Assert-PortableFile([string]$Root,[string]$Relative,[string]$Hash) {
        $path=[IO.Path]::GetFullPath([IO.Path]::Combine($Root,$Relative))
        if(-not $path.StartsWith($Root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Source binding leaves the release root.'
        }
        Assert-FileHash $path $Hash
    }
    foreach($name in @('H3_Base_145125','H3_Retained_145125','Original_153000_BestQualified','Original_155250')) {
        $release=[IO.Path]::Combine($cpu,$name)
        $recipe=Get-ReleaseRecipe $release
        $performance=Get-Content -LiteralPath ([IO.Path]::Combine($release,'PERFORMANCE.json')) -Raw|ConvertFrom-Json
        foreach($binding in @($recipe.source_copies)+@($recipe.simulation.sources)) {
            Assert-PortableFile $release $binding.portable $binding.sha256
            $sourceChecks++
        }
        foreach($role in @('V0','V1')) {
            $image=$recipe.roles.$role
            Assert-PortableFile $release $image.bitstream $image.bitstream_sha256
            Assert-PortableFile $release $image.firmware_hex $image.firmware_sha256
            Assert-PortableFile $release $image.reference_uart $image.reference_uart_sha256
            foreach($capture in $image.board_originals) {
                Assert-PortableFile $release $capture.portable $capture.sha256
                $raw=[IO.Path]::Combine($release,$capture.portable)
                $audit=[IO.Path]::Combine($output,($name+'-'+$role+'-'+($captures+1)+'-board.json'))
                & ([IO.Path]::Combine($scripts,'Audit-BoardCapture.ps1')) -ReleaseRoot $release -Role $role -RawCapture $raw -OutputPath $audit
                if($LASTEXITCODE -ne 0){throw 'Complete board-frame audit failed.'}
                $record=Get-Content -LiteralPath $audit -Raw|ConvertFrom-Json
                $expected=$performance|Where-Object configuration -eq $role
                if($record.Cycles -ne $expected.cycles -or $record.Retired -ne $expected.retired -or [Math]::Abs($record.CoreMark-$expected.coremark) -gt 0.000001) {
                    throw 'Performance documentation does not match a packaged board capture.'
                }
                $captures++
            }
            $physical=[IO.Path]::Combine($release,'evidence','physical',$role,'implementation')
            $timing=[IO.Path]::Combine($physical,'report_timing','pds_soc_top.rtr')
            & ([IO.Path]::Combine($scripts,'Audit-Timing.ps1')) -ReportPath $timing -OutputPath ([IO.Path]::Combine($output,($name+'-'+$role+'-timing.json')))
            if($LASTEXITCODE -ne 0){throw 'Archived timing report failed.'}
            $reports++
            $physicalSummary=Get-Content -LiteralPath ([IO.Path]::Combine($physical,'resource-timing-summary.json')) -Raw|ConvertFrom-Json
            if(-not $physicalSummary.constraints_met -or $physicalSummary.clock_hz -ne $recipe.clock_hz){throw 'Physical clock or timing status does not match the recipe.'}
            $expected=$performance|Where-Object configuration -eq $role
            if($expected.lut -ne $physicalSummary.resources.post_route_luts -or $expected.ff -ne $physicalSummary.resources.post_route_ffs){throw 'Documented resources differ from the archived physical report.'}
            $summary.Add(@{release=$name;role=$role;captures=3;timing='passed';lut=$expected.lut;coremark=$expected.coremark})
        }
    }
    $ila=[IO.Path]::Combine($cpu,'Accepted_RV32IM_153000_FullILA')
    $archiveCount=0
    foreach($entry in Import-Csv -LiteralPath ([IO.Path]::Combine($ila,'EXTRACTED_FILE_MANIFEST.csv'))) {
        Assert-PortableFile $ila $entry.Path $entry.SHA256
        $path=[IO.Path]::Combine($ila,$entry.Path)
        if((Get-Item -LiteralPath $path).Length -ne [long]$entry.Bytes){throw 'ILA original archive payload size changed.'}
        $archiveCount++
    }
    if($archiveCount -ne 1703){throw 'Expected all 1,703 recovered ILA payloads.'}
    $resultRoot=[IO.Path]::Combine($ila,'project','cpu_paper','results')
    $reviewFile=Get-ChildItem -LiteralPath $resultRoot -Recurse -Filter review.json -File|Where-Object FullName -match 'selected-coremark-board-review'|Select-Object -First 1
    $review=Get-Content -LiteralPath $reviewFile.FullName -Raw|ConvertFrom-Json
    if(-not $review.qualified -or $review.full_rtl_pending -or $review.rows.Count -ne 6){throw 'ILA final joint board/RTL qualification is incomplete.'}
    $ilaMetrics=Get-Content -LiteralPath ([IO.Path]::Combine($ila,'PERFORMANCE.json')) -Raw|ConvertFrom-Json
    foreach($row in $review.rows) {
        $metric=$ilaMetrics|Where-Object configuration -eq $row.configuration
        if(-not $row.crc_valid -or $row.cycles -ne $metric.cycles -or $row.retired -ne $metric.retired){throw 'ILA qualification and performance data differ.'}
    }
    $physical=Get-ChildItem -LiteralPath $resultRoot -Directory|Where-Object Name -match '^physical-redirect-accepted_valid_ram-uart-loader'
    $timing=[IO.Path]::Combine($physical.FullName,'implementation','report_timing','pds_soc_top.rtr')
    & ([IO.Path]::Combine($scripts,'Audit-Timing.ps1')) -ReportPath $timing -OutputPath ([IO.Path]::Combine($output,'ILA-timing.json'))
    if($LASTEXITCODE -ne 0){throw 'ILA timing audit failed.'}
    $reports++
    $originalSbit=[IO.Path]::Combine($physical.FullName,'implementation','generate_bitstream','pds_soc_top.sbit')
    $convenience=[IO.Path]::Combine($ila,'bitstreams','FullILA_153MHz.sbit')
    if((Get-FileHash -LiteralPath $originalSbit).Hash -ne (Get-FileHash -LiteralPath $convenience).Hash){throw 'ILA convenience bitstream differs from the archived bitstream.'}
    $scriptFiles=@(Get-ChildItem -LiteralPath $scripts -Filter '*.ps1' -File)+@(Get-ChildItem -LiteralPath $ila -Filter '*.ps1' -File)+@(Get-Item -LiteralPath $PSCommandPath)
    foreach($file in $scriptFiles) {
        $tokens=$null;$parseErrors=$null
        $null=[Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$parseErrors)
        if($parseErrors.Count){throw ('PowerShell parse error in '+$file.Name)}
    }
    $result=[ordered]@{status='passed';tested_utc=[DateTime]::UtcNow.ToString('o');rv32imc_releases=4;ila_releases=1;rv32imc_capture_audits=$captures;ila_qualified_observations=$review.rows.Count;ila_original_payload_hashes=$archiveCount;source_bindings=$sourceChecks;timing_reports=$reports;timing_sections=$reports*10;clock_uncertainty_ns=0.150;powershell_scripts_parsed=$scriptFiles.Count;results=$summary.ToArray();scope='Offline archive, source, measurement and timing validation; no new PDS route, full simulation or board execution.'}
    $report=[IO.Path]::Combine($output,'RESULT.json')
    [IO.File]::WriteAllText($report,($result|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($true))
    Write-Output ('Passed: {0} board frames, {1} ILA observations, {2} ILA payload hashes and {3} timing reports. Report: {4}' -f $captures,$review.rows.Count,$archiveCount,$reports,$report)
    exit 0
} catch {Write-Error $_;exit 1}
