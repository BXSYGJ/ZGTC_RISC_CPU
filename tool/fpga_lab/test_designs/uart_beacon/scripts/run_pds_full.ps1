<#
  uart_beacon PDS 全流程构建。用法：pwsh -NoProfile -File .\scripts\run_pds_full.ps1
#>
param(
    [string]$ProjectName = 'uart_beacon',
    [string]$TopModule   = 'uart_beacon'
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

try {
    $pdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'Process')
    if ([string]::IsNullOrWhiteSpace($pdsRoot)) {
        $pdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'User')
    }
    if ([string]::IsNullOrWhiteSpace($pdsRoot)) {
        $pdsRoot = 'H:\GG\pango\PDS_2022.2-SP6.4'
    }
    $projectRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $pdsShell = Join-Path $pdsRoot 'bin\pds_shell.exe'
    $template = Join-Path $PSScriptRoot 'build_full.tcl'
    $localTcl = Join-Path $PSScriptRoot 'build_full.local.tcl'
    if (-not (Test-Path -LiteralPath $pdsShell)) { throw "PDS shell not found: $pdsShell" }
    $env:PANGO_LICENSE_FILE = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) { throw 'PANGO_LICENSE_FILE not set.' }

    $content = [System.IO.File]::ReadAllText($template)
    $rootFwd = $projectRoot.Replace('\', '/')
    [System.IO.File]::WriteAllText($localTcl, $content.Replace('__PROJECT_ROOT__', $rootFwd),
                                   [System.Text.UTF8Encoding]::new($false))
    $out = & $pdsShell -file $localTcl -work_dir $projectRoot -project_name $ProjectName 2>&1
    $out | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { throw "PDS failed exit=$LASTEXITCODE" }
    if ($out | Select-String -Pattern '^E:') { throw 'PDS reported E: errors' }
    $bit = Join-Path $projectRoot "generate_bitstream\$TopModule.sbit"
    if (-not (Test-Path -LiteralPath $bit)) { throw "missing bitstream: $bit" }
    Write-Output "Bitstream: $bit"
    Write-Output "SHA-256: $((Get-FileHash -LiteralPath $bit -Algorithm SHA256).Hash)"
} catch {
    Write-Error $_
    exit 1
}
