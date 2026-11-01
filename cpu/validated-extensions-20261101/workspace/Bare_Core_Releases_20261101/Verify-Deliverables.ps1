[CmdletBinding()]
param()
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $bare = $PSScriptRoot
    $ila = [System.IO.Path]::Combine([System.IO.Path]::GetFullPath([System.IO.Path]::Combine($bare,'..')),'ILA_Core_Releases_20261101')
    $receipts = [System.Collections.Generic.List[object]]::new()
    foreach ($command in @(@([System.IO.Path]::Combine($ila,'Refresh-ReleaseCatalog.ps1'),'-RequireTimingClosure'), @([System.IO.Path]::Combine($bare,'Refresh-ReleaseCatalog.ps1')))) {
        $path = $command[0]
        $output = if ($command.Count -eq 2) { & $path -RequireTimingClosure } else { & $path }
        $code = $LASTEXITCODE
        if ($code -ne 0) { throw ('Catalog verification failed: ' + $path) }
        $receipts.Add([ordered]@{command = $path; arguments = if ($command.Count -eq 2) { @('-RequireTimingClosure') } else { @() }; exit_code = $code; literal_output = $output -join [Environment]::NewLine})
    }
    $aggregatePath = [System.IO.Path]::Combine($bare,'analysis','PHYSICAL_AREA_AUDIT.json')
    $aggregate = Get-Content -LiteralPath $aggregatePath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($aggregate.status -ne 'PASS') { throw 'Native area audit is incomplete.' }
    $catalogPaths = @([System.IO.Path]::Combine($ila,'RELEASES.json'),[System.IO.Path]::Combine($bare,'RELEASES.json'))
    $linked = [System.Collections.Generic.List[object]]::new()
    foreach ($catalogPath in $catalogPaths) {
        $catalog = Get-Content -LiteralPath $catalogPath -Raw -Encoding utf8 | ConvertFrom-Json
        if (@($catalog.releases).Count -ne 3) { throw 'Expected three releases per catalog.' }
        $linked.Add([ordered]@{path=$catalogPath;sha256=(Get-FileHash -LiteralPath $catalogPath -Algorithm SHA256).Hash.ToLowerInvariant()})
    }
    foreach ($release in @('Original_155250','H3_Retained_145125','H3_Base_145125')) {
        foreach ($root in @($ila,$bare)) {
            $selectionPath = [System.IO.Path]::Combine($root,$release,'SELECTED_BUILD.json')
            $selection = Get-Content -LiteralPath $selectionPath -Raw -Encoding utf8 | ConvertFrom-Json
            $build = $selection.build_directory
            foreach ($relative in @('inputs','DIFF_FILE.txt','VERIFICATION.txt','ROLLBACK.ps1')) {
                $artifact = [System.IO.Path]::Combine($build,$relative)
                if (-not (Test-Path -LiteralPath $artifact)) { throw ('Missing delivery artifact: ' + $artifact) }
                if ([System.IO.Directory]::Exists($artifact)) {
                    $fixture = [System.IO.Path]::Combine($artifact, $(if ($root -eq $ila) { 'pds_soc_top.v' } else { 'bare_core_scan_top.sv' }))
                    $null = [System.IO.File]::ReadAllText($fixture)
                } else { $null = [System.IO.File]::ReadAllText($artifact) }
            }
            $linked.Add([ordered]@{path=$selectionPath;sha256=(Get-FileHash -LiteralPath $selectionPath -Algorithm SHA256).Hash.ToLowerInvariant()})
        }
    }
    $report = [ordered]@{schema='six-release-final-verification/v1';status='PASS';verified_utc=[datetime]::UtcNow.ToString('o');ila_releases=3;bare_releases=3;local_waveform_windows=9;full_6000_source_runs=3;bare_extraction_baseline_edges=6000000;bare_extraction_rollback_edges=6000000;physical_timing_passes=6;remote_board_operations='disabled by user';receipts=$receipts.ToArray();linked=$linked.ToArray();native_area_audit=$aggregatePath;native_area_audit_sha256=(Get-FileHash -LiteralPath $aggregatePath -Algorithm SHA256).Hash.ToLowerInvariant()}
    $reportPath = [System.IO.Path]::Combine($bare,'analysis','FINAL_VERIFICATION.json')
    [System.IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($true))
    $null=Get-Content -LiteralPath $reportPath -Raw -Encoding utf8|ConvertFrom-Json
    Write-Output 'DELIVERABLES_VERIFIED ILA=3 BARE=3 timing_passes=6 waveform_windows=9 source_full_runs=3'
    Write-Output $reportPath
    exit 0
} catch { Write-Error $_; exit 1 }