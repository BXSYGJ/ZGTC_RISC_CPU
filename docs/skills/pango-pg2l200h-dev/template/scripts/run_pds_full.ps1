<#
  PG2L200H PDS 全流程批处理入口。
  用法：在 PG2L200H 工程根目录执行
        pwsh -NoProfile -File .\scripts\run_pds_full.ps1
  依赖：PDS_ROOT（缺省回退本机 H:\GG\pango\PDS_2022.2-SP6.4）与
        PANGO_LICENSE_FILE（用户级环境变量，指向 .lic 绝对路径）。
  本脚本仅展开 build_full.tcl 中的 __PROJECT_ROOT__ 令牌并调用 pds_shell，
  不启动图形界面。不执行任何远程/上板操作。
#>

param(
    [string]$ProjectName = 'blink_200h',
    [string]$TopModule   = 'blink_top'
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

try {
    $configuredPdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'Process')
    if ([string]::IsNullOrWhiteSpace($configuredPdsRoot)) {
        $configuredPdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'User')
    }
    if ([string]::IsNullOrWhiteSpace($configuredPdsRoot)) {
        $pdsRoot = [System.IO.Path]::Combine('H:', 'GG', 'pango', 'PDS_2022.2-SP6.4')
    } else {
        $pdsRoot = [System.IO.Path]::GetFullPath($configuredPdsRoot)
    }
    $projectRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $pdsShell = [System.IO.Path]::Combine($PdsRoot, 'bin', 'pds_shell.exe')
    $buildTemplate = [System.IO.Path]::Combine($PSScriptRoot, 'build_full.tcl')
    $buildScript = [System.IO.Path]::Combine($PSScriptRoot, 'build_full.local.tcl')

    if (-not (Test-Path -LiteralPath $pdsShell -PathType Leaf)) {
        throw "PDS shell not found: $pdsShell"
    }
    if (-not (Test-Path -LiteralPath $buildTemplate -PathType Leaf)) {
        throw "PDS build template not found: $buildTemplate"
    }

    $env:PANGO_LICENSE_FILE = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) {
        throw 'PANGO_LICENSE_FILE is not configured in the current user environment.'
    }

    $templateContent = [System.IO.File]::ReadAllText($buildTemplate)
    if (-not $templateContent.Contains('__PROJECT_ROOT__')) {
        throw 'PDS build template does not contain the required project-root token.'
    }
    $tclProjectRoot = $projectRoot.Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    $localBuildContent = $templateContent.Replace('__PROJECT_ROOT__', $tclProjectRoot)
    [System.IO.File]::WriteAllText($buildScript, $localBuildContent, [System.Text.UTF8Encoding]::new($false))

    $pdsOutput = & $pdsShell -file $buildScript -work_dir $projectRoot -project_name $ProjectName 2>&1
    $pdsOutput | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "PDS full flow failed with exit code $LASTEXITCODE."
    }
    if ($pdsOutput | Select-String -Pattern '^E:') {
        throw 'PDS reported one or more tool errors even though its process exit code was zero.'
    }

    $bitstream = [System.IO.Path]::Combine($projectRoot, 'generate_bitstream', "$TopModule.sbit")
    if (-not (Test-Path -LiteralPath $bitstream -PathType Leaf)) {
        throw "PDS completed without the expected bitstream: $bitstream"
    }

    $hash = Get-FileHash -LiteralPath $bitstream -Algorithm SHA256
    Write-Output "Bitstream: $bitstream"
    Write-Output "SHA-256: $($hash.Hash)"
} catch {
    Write-Error $_
    exit 1
}
