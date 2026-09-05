[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = 'Stop'

try {
    $distribution = 'Ubuntu-22.04'
    $projectRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $sourcePath = [System.IO.Path]::Combine($projectRoot, 'src', 'blink_top.v')
    $testbenchPath = [System.IO.Path]::Combine($projectRoot, 'sim', 'blink_top_tb.v')
    $outputDirectory = [System.IO.Path]::Combine($projectRoot, 'sim_out')
    $outputPath = [System.IO.Path]::Combine($outputDirectory, 'blink_top_tb.vvp')

    foreach ($path in @($sourcePath, $testbenchPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required source file not found: $path"
        }
    }

    [void](New-Item -ItemType Directory -Path $outputDirectory -Force)

    $wslSource = (& wsl.exe --distribution $Distribution --exec /usr/bin/wslpath -a $sourcePath).Trim()
    $wslTestbench = (& wsl.exe --distribution $Distribution --exec /usr/bin/wslpath -a $testbenchPath).Trim()
    $wslOutput = (& wsl.exe --distribution $Distribution --exec /usr/bin/wslpath -a $outputPath).Trim()

    & wsl.exe --distribution $Distribution --exec /usr/bin/iverilog -g2012 -Wall -s blink_top_tb -o $wslOutput $wslSource $wslTestbench
    if ($LASTEXITCODE -ne 0) {
        throw "Icarus Verilog compilation failed with exit code $LASTEXITCODE."
    }

    & wsl.exe --distribution $Distribution --exec /usr/bin/vvp $wslOutput
    if ($LASTEXITCODE -ne 0) {
        throw "RTL simulation failed with exit code $LASTEXITCODE."
    }

    Write-Output 'WSL RTL simulation completed successfully.'
} catch {
    Write-Error $_
    exit 1
}
