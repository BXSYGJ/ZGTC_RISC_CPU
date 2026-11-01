param([Parameter(Mandatory)][string]$BuildDirectory,[Parameter(Mandatory)][string]$DestinationDirectory)
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try{
    $build=[System.IO.Path]::GetFullPath($BuildDirectory);$frozen=[System.IO.Path]::Combine($build,'frozen_inputs');$destination=[System.IO.Path]::GetFullPath($DestinationDirectory)
    if($destination -eq $build -or $destination.StartsWith(([System.IO.Path]::Combine($build,'inputs')+[System.IO.Path]::DirectorySeparatorChar),[StringComparison]::OrdinalIgnoreCase) -or $destination -eq [System.IO.Path]::Combine($build,'inputs')){throw 'Rollback destination must be a separate review copy.'}
    if(Test-Path -LiteralPath $destination){throw 'Rollback destination already exists.'}
    $files=@(Get-ChildItem -LiteralPath $frozen -File);if($files.Count -ne 8){throw 'Frozen rollback closure must contain exactly eight files.'}
    [void][System.IO.Directory]::CreateDirectory($destination)
    foreach($file in $files){$target=[System.IO.Path]::Combine($destination,$file.Name);Copy-Item -LiteralPath $file.FullName -Destination $target;if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash){throw ('Restored file hash differs: '+$file.Name)}}
    foreach($file in Get-ChildItem -LiteralPath $destination -File){[void][System.IO.File]::ReadAllBytes($file.FullName)}
    Write-Output 'ROLLBACK_PASS restored_files=8';exit 0
}catch{Write-Error -Message $_.Exception.Message -ErrorAction Continue;exit 1}
