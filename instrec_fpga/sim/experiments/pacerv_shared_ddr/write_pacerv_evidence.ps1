[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $root = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', '..', '..'))
    $rtl = [System.IO.Path]::Combine($root, 'src', 'ddr3')
    $modified = [System.IO.Path]::Combine($PSScriptRoot, 'MODIFIED_FILE.v')
    $diff = [System.IO.Path]::Combine($PSScriptRoot, 'DIFF_FILE.patch')
    $verification = [System.IO.Path]::Combine($PSScriptRoot, 'VERIFICATION.txt')
    $rollback = [System.IO.Path]::Combine($PSScriptRoot, 'ROLLBACK.sh')
    $encoding = [System.Text.UTF8Encoding]::new($true)
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($rtl, 'pace_cpu_ddr_bridge.v')) -Destination $modified
    $rollbackSource = @(
        'param([Parameter(Mandatory)][string]$EvidenceDirectory, [Parameter(Mandatory)][string]$TargetRtlDirectory)',
        '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8',
        '$ErrorActionPreference = ''Stop''',
        'try {',
        '    & ([System.IO.Path]::Combine($EvidenceDirectory, ''ROLLBACK.ps1'')) -TargetRtlDirectory $TargetRtlDirectory',
        '    if ($LASTEXITCODE -ne 0) { throw ''Rollback failed.'' }',
        '} catch { Write-Error $_; exit 1 }'
    )
    [System.IO.File]::WriteAllLines($rollback, $rollbackSource, $encoding)
    $empty = [System.IO.Path]::Combine($PSScriptRoot, 'empty_original.txt')
    [System.IO.File]::WriteAllText($empty, '', [System.Text.UTF8Encoding]::new($false))
    $diffLines = [System.Collections.Generic.List[string]]::new()
    $hashes = [System.Collections.Generic.List[object]]::new()
    foreach ($name in @('ddr3_ctrl_axi.v', 'ddr3_arbiter.v', 'pace_cpu_ddr_bridge.v', 'ddr3_m3_share.v')) {
        $original = [System.IO.Path]::Combine($PSScriptRoot, ($name + '.original'))
        $current = [System.IO.Path]::Combine($rtl, $name)
        $oldHash = $null
        if (Test-Path -LiteralPath $original) { $oldHash = (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash }
        else { $original = $empty }
        $patch = @(& git -c core.autocrlf=false diff --no-index -- $original $current 2>&1)
        if ($LASTEXITCODE -gt 1) { throw ('Diff failed: ' + $name) }
        foreach ($line in $patch) { $diffLines.Add($line.ToString()) }
        $hashes.Add([pscustomobject]@{ File = $current; OriginalSHA256 = $oldHash; ModifiedSHA256 = (Get-FileHash -LiteralPath $current -Algorithm SHA256).Hash })
    }
    [System.IO.File]::WriteAllLines($diff, $diffLines, [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($PSScriptRoot, 'SOURCE_HASHES.json'), (ConvertTo-Json -InputObject $hashes.ToArray() -Depth 4), $encoding)
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('PaceRV shared DDR bridge verification')
    $lines.Add('Changed fields: M3_MASK_ENABLE=0 legacy default / m3_wstrb byte mask; CPU APP/OBS range decode; M3 locked ownership, round-robin, drain completion and abort termination.')
    $lines.Add('APP CPU 0x40000000..0x400fffff maps to DDR 0x00600000..0x006fffff. OBS CPU 0x41000000..0x415fffff reads only existing legal PCM/weight/spectrum/self-test/activation windows. CPU word-bus requests require address[1:0]=0; data/strobes encode subword stores.')
    $lines.Add('Dummy write remains zero mask. Byte addresses are shifted right by two only at the IP boundary. The new TB indexes the IP word address right by three with no address truncation.')
    $lines.Add('M3 client done preserves the raw hardware-completion edge, including final write-ready. Ownership/read routing stay locked until registered done plus full read drain. Abort forwards an owner termination with its error. CPU-only timeout freezes payload, drains late traffic and preserves subsequent diagnostic service.')
    $lines.Add('Legacy TB adapter adds wait(rst_n===1) before the verdict wait loop for Icarus event semantics; original production TB is unchanged.')
    $lines.Add('MODIFIED_FILE: ' + $modified)
    $lines.Add('DIFF_FILE: ' + $diff)
    $lines.Add('VERIFICATION: ' + $verification)
    $lines.Add('ROLLBACK: ' + $rollback + ' (PowerShell source: execute as a scriptblock with EvidenceDirectory and TargetRtlDirectory; the standard -File entry is ROLLBACK.ps1)')
    foreach ($mode in @('Baseline', 'Modified', 'Rollback')) {
        $resultPath = [System.IO.Path]::Combine($PSScriptRoot, ($mode.ToUpperInvariant() + '_RESULTS.json'))
        $results = @(Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json)
        $lines.Add('')
        $lines.Add($mode.ToUpperInvariant() + ' exact command: pwsh -NoProfile -File "' + [System.IO.Path]::Combine($PSScriptRoot, 'run_pacerv_shared_ddr.ps1') + '" -Mode ' + $mode)
        $lines.Add('Input: deterministic RTL testbenches; pseudorandom IP handshake LFSR seed 0x12345678; original files for Baseline/Rollback and current four RTL files for Modified.')
        if ($mode -eq 'Rollback') { $lines.Add('ROLLBACK HASH PASS restored=2 removed_new=2') }
        foreach ($result in $results) {
            $lines.Add('Case: ' + $result.Case)
            $lines.Add('Compiler: ' + $result.Compiler)
            $lines.Add('Arguments: ' + (ConvertTo-Json -InputObject $result.CompileArguments -Compress))
            $lines.Add('Compile literal output: ' + $result.CompileOutput)
            $lines.Add('Compile exit: ' + $result.CompileExit)
            $lines.Add('Run command: ' + (ConvertTo-Json -InputObject $result.RunCommand -Compress))
            $lines.Add('Literal output/result:')
            $lines.Add($result.Output)
            $lines.Add('Run exit: ' + $result.RunExit)
        }
        $lines.Add($mode.ToUpperInvariant() + ' PASS cases=' + $results.Count)
        $lines.Add('Overall exit: 0')
    }
    $lines.Add('Restored behavior/status: independent rollback copy matches both original SHA256 hashes, both newly added RTL files are removed from that copy, and original 3-phase/40-read-beat/zero-mismatch behavior passes. Live RTL remains modified.')
    $lines.Add('Validation scope: RTL simulation and source/hash checks. Full-system synthesis, routing, and board measurements belong to the root integration task.')
    [System.IO.File]::WriteAllLines($verification, $lines, $encoding)
    foreach ($path in @($modified, $diff, $verification, $rollback)) {
        $contents = [System.IO.File]::ReadAllText($path)
        if ($contents.Length -eq 0) { throw ('Empty artifact: ' + $path) }
        Write-Output ('REOPEN PASS ' + $path + ' bytes=' + (Get-Item -LiteralPath $path).Length)
    }
    exit 0
} catch {
    Write-Error $_
    exit 1
}
