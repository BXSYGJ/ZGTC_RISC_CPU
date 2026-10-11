[CmdletBinding()]
param([Parameter(Mandatory)][string]$ReleaseRoot,[Parameter(Mandatory)][string]$TargetDirectory,[Parameter(Mandatory)][ValidateLength(5,1000)][string]$Purpose)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot,'Common.ps1'))
    $source = Get-FullPath $ReleaseRoot
    $target = Get-FullPath $TargetDirectory
    if (Test-Path -LiteralPath $target) { throw 'Experiment target must be a new directory' }
    if ($target.StartsWith($source+[System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Create the experiment outside the frozen release' }
    $recipe = Get-ReleaseRecipe $source
    Copy-Item -LiteralPath $source -Destination $target -Recurse
    $baseline = foreach ($file in Get-ChildItem -LiteralPath $source -File -Recurse) {
        @{Path=[System.IO.Path]::GetRelativePath($source,$file.FullName).Replace([char]92,[char]47);Bytes=$file.Length;SHA256=(Get-FileHash -LiteralPath $file.FullName).Hash}
    }
    Write-Json @{Schema='experiment-fork/v1';CreatedUtc=[DateTime]::UtcNow.ToString('o');Purpose=$Purpose;FrozenParent=$recipe.release;ParentRecipeSHA256=(Get-FileHash -LiteralPath ([System.IO.Path]::Combine($source,'recipe.json'))).Hash;BaselineFiles=$baseline;Status='Prepared; no new performance or timing result';Variables=@();Workloads=@();Measurements=@()} ([System.IO.Path]::Combine($target,'EXPERIMENT.json'))
    Write-Output "Experiment copy created: $target. Frozen originals remain unchanged."
    exit 0
} catch {Write-Error $_;exit 1}
