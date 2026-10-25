#requires -Version 7.0
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $root = $PSScriptRoot
    $core = [System.IO.Path]::Combine($root, 'vision-core')
    $evidence = [System.IO.Path]::Combine($root, 'recovered')
    $manifest = Import-Csv -LiteralPath ([System.IO.Path]::Combine($evidence, 'vision-core-manifest.csv')) -Encoding utf8
    foreach ($entry in $manifest) {
        $file = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($core, $entry.RelativePath))
        if (-not $file.StartsWith($core + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'A manifest path leaves the recovery directory.'
        }
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.SHA256) {
            throw ('Core SHA256 mismatch: ' + $entry.RelativePath)
        }
    }
    $datasetManifest = Get-Content -LiteralPath ([System.IO.Path]::Combine($evidence, 'dataset-file-manifest.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    foreach ($entry in $datasetManifest) {
        $file = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($core, $entry.relative_path))
        if (-not $file.StartsWith($core + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'A dataset path leaves the recovery directory.'
        }
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) {
            throw ('Dataset SHA256 mismatch: ' + $entry.relative_path)
        }
    }
    $datasetAudit = Get-Content -LiteralPath ([System.IO.Path]::Combine($evidence, 'dataset-audit.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not $datasetAudit.structural_checks_pass) { throw 'Dataset structural audit did not pass.' }
    $archiveVerified = $false
    if (Test-Path -LiteralPath $datasetAudit.archive) {
        $archiveHash = (Get-FileHash -LiteralPath $datasetAudit.archive -Algorithm SHA256).Hash
        if ($archiveHash -ne $datasetAudit.archive_sha256) { throw 'Source ZIP SHA256 mismatch.' }
        $archiveVerified = $true
    }
    $inspection = Get-Content -LiteralPath ([System.IO.Path]::Combine($evidence, 'model-inspection.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    if ($inspection.onnx_checker -ne 'PASS' -or $inspection.real_image_inference.result -ne 'PASS') {
        throw 'Stored model validation did not pass.'
    }
    $checkpointReport = [System.IO.Path]::Combine($evidence, 'checkpoint-inspection.json')
    $log = [System.IO.Path]::Combine($evidence, 'checkpoint-recheck.stdout.log')
    & python ([System.IO.Path]::Combine($evidence, 'inspect_checkpoint.py')) $core $checkpointReport | Out-File -LiteralPath $log -Encoding utf8BOM
    if ($LASTEXITCODE -ne 0) { throw 'Checkpoint and training inputs recheck failed.' }
    $result = [ordered]@{
        result = 'PASS'
        core_files_sha256_verified = @($manifest).Count
        dataset_files_sha256_verified = @($datasetManifest).Count
        archive_sha256_verified = $archiveVerified
        train_images = $datasetAudit.splits.train.images
        val_images = $datasetAudit.splits.val.images
        field_images = $datasetAudit.image_directories.'images/field'
        images_in_all_folders = $datasetAudit.images_total_including_field_and_backups
        checkpoint_and_training_inputs_rechecked = $true
    }
    $json = $result | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($evidence, 'FINAL_VERIFICATION.json'), $json, [System.Text.UTF8Encoding]::new($true))
    $json
} catch {
    Write-Error $_
    exit 1
}
