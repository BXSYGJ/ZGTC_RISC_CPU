[CmdletBinding()]
param(
    [Parameter()]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Container })]
    [string]$Directory = $PSScriptRoot,
    [Parameter()]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$RemoteCommit,
    [Parameter()]
    [string]$ReceiptPath
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'

try {
    $archiveRoot = [System.IO.Path]::GetFullPath($Directory)
    $checksums = [System.IO.Path]::Combine($archiveRoot, 'SHA256SUMS.txt')
    $results = [System.Collections.Generic.List[object]]::new()
    $fileCount = 0
    foreach ($line in Get-Content -LiteralPath $checksums -Encoding utf8) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -notmatch '^([0-9a-fA-F]{64})\s+([A-Za-z0-9_.-]+[.]zip)$') {
            throw 'Invalid checksum entry.'
        }
        $expectedHash = $Matches[1].ToLowerInvariant()
        $archiveName = $Matches[2]
        $archivePath = [System.IO.Path]::Combine($archiveRoot, $archiveName)
        $sourceUrl = $null
        if ($RemoteCommit) {
            $cacheRoot = [System.IO.Path]::Combine($archiveRoot, 'remote-verification', $RemoteCommit)
            [System.IO.Directory]::CreateDirectory($cacheRoot) | Out-Null
            $archivePath = [System.IO.Path]::Combine($cacheRoot, $archiveName)
            $sourceUrl = 'https://raw.githubusercontent.com/BXSYGJ/ZGTC_RISC_CPU/' + $RemoteCommit + '/releases/pacerv-145125/' + $archiveName
            Invoke-WebRequest -Uri $sourceUrl -OutFile $archivePath
        }
        $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -cne $expectedHash) { throw ('ZIP SHA256 mismatch: ' + $archiveName) }
        $archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
        try {
            $entries = @($archive.Entries | Where-Object { -not $_.FullName.EndsWith('/') })
            $nameSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
            foreach ($entry in $entries) {
                if (-not $nameSet.Add($entry.FullName)) { throw 'Duplicate ZIP entry.' }
            }
            $manifestEntry = $archive.GetEntry('MANIFEST.json')
            if ($null -eq $manifestEntry) {
                $manifestEntry = $archive.GetEntry(([System.IO.Path]::GetFileNameWithoutExtension($archiveName) + '/MANIFEST.json'))
            }
            if ($null -eq $manifestEntry) { throw ('Root manifest missing: ' + $archiveName) }
            $prefix = $manifestEntry.FullName.Substring(0, $manifestEntry.FullName.Length - 'MANIFEST.json'.Length)
            $reader = [System.IO.StreamReader]::new($manifestEntry.Open(), [System.Text.Encoding]::UTF8, $true)
            try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            $manifestNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
            foreach ($item in $manifest.files) {
                $relative = [string]$item.path
                if ($relative -match '(^/|(^|/)[.][.](/|$)|[\\:])' -or -not $manifestNames.Add($relative)) {
                    throw 'Unsafe or duplicate manifest path.'
                }
                $entry = $archive.GetEntry(($prefix + $relative))
                if ($null -eq $entry -or $entry.Length -ne $item.bytes) { throw ('Size mismatch: ' + $relative) }
                $stream = $entry.Open()
                try { $entryHash = [System.Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant() }
                finally { $stream.Dispose() }
                if ($entryHash -cne ([string]$item.sha256).ToLowerInvariant()) { throw ('Entry SHA256 mismatch: ' + $relative) }
            }
            if ($entries.Count -ne ($manifestNames.Count + 1)) { throw 'ZIP inventory mismatch.' }
            $fileCount += $manifestNames.Count
            $results.Add([PSCustomObject]@{
                name = $archiveName; sha256 = $actualHash; bytes = (Get-Item -LiteralPath $archivePath).Length
                manifest_files = $manifestNames.Count; manifest = 'PASS'; source_url = $sourceUrl
            })
        } finally { $archive.Dispose() }
    }
    if ($results.Count -eq 0) { throw 'No archive checksums found.' }
    $receipt = [PSCustomObject]@{
        checked_utc = [DateTimeOffset]::UtcNow.ToString('o'); status = 'PASS'; remote_commit = $RemoteCommit
        archive_count = $results.Count; manifest_file_count = $fileCount; archives = $results.ToArray(); exit_status = 0
    }
    if ($ReceiptPath) {
        $receiptFile = [System.IO.Path]::GetFullPath($ReceiptPath)
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($receiptFile)) | Out-Null
        [System.IO.File]::WriteAllText($receiptFile, (($receipt | ConvertTo-Json -Depth 8) + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($true))
    }
    Write-Output ('ARCHIVE_VERIFY_PASS archives=' + $results.Count + ' files=' + $fileCount)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
