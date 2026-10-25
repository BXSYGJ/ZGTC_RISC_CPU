param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$WorkDirectory,
    [ValidateNotNullOrEmpty()][string]$PdsHome = 'D:/PDS_2022.2-SP6.4',
    [switch]$RunPds
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $encoding = [System.Text.UTF8Encoding]::new($true)
    $results = [System.IO.Path]::Combine($PSScriptRoot, 'project', 'cpu_paper', 'results')
    $physicalName = 'physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1'
    $source = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($results, $physicalName))
    $destination = [System.IO.Path]::GetFullPath($WorkDirectory)
    $packageRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
    if ($destination.StartsWith($packageRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Use a working directory outside this evidence package.'
    }
    if (Test-Path -LiteralPath $destination) { throw 'Working directory already exists; choose a new directory.' }
    New-Item -ItemType Directory -Path $destination | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $destination -Recurse -Force
    $oldPrefix = 'D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/' + $physicalName
    $newPrefix = $destination.Replace([char]92, [char]47)
    $changed = [System.Collections.Generic.List[string]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $destination -Recurse -File) {
        if ($file.Extension -notin @('.tcl', '.pds', '.fic', '.v', '.sv', '.fdc')) { continue }
        $original = [System.IO.File]::ReadAllText($file.FullName)
        $updated = $original.Replace($oldPrefix, $newPrefix)
        if ($updated -cne $original) {
            [System.IO.File]::WriteAllText($file.FullName, $updated, $encoding)
            $changed.Add([System.IO.Path]::GetRelativePath($destination, $file.FullName))
        }
    }
    $implementation = [System.IO.Path]::Combine($destination, 'implementation')
    $shell = [System.IO.Path]::Combine($PdsHome, 'bin', 'pds_shell.exe')
    $build = [System.IO.Path]::Combine($implementation, 'build.tcl')
    $receipt = [ordered]@{
        prepared_utc = [DateTime]::UtcNow.ToString('o')
        source_directory = $source
        working_directory = $destination
        changed_text_files = @($changed)
        scope = 'Reimplementation from frozen synthesized netlist and ADF; not fresh RTL synthesis.'
        pds_invoked = $false
    }
    $receiptPath = [System.IO.Path]::Combine($destination, 'RELOCATION_RECEIPT.json')
    [System.IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 8), $encoding)
    if ($RunPds) {
        if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) { throw "PDS shell missing: $shell" }
        $start = [System.Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $shell
        $start.WorkingDirectory = $implementation
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        foreach ($argument in @('-file', $build, '-work_dir', $implementation, '-project_name', 'cpu_ila')) {
            $start.ArgumentList.Add($argument)
        }
        $process = [System.Diagnostics.Process]::Start($start)
        $process.WaitForExit()
        $receipt.pds_invoked = $true
        $receipt['pds_exit_code'] = $process.ExitCode
        [System.IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 8), $encoding)
        if ($process.ExitCode -ne 0) { throw "PDS exited with code $($process.ExitCode). Inspect working-directory logs." }
    }
    Write-Output "Prepared working project: $implementation"
} catch {
    Write-Error $_
    exit 1
}
