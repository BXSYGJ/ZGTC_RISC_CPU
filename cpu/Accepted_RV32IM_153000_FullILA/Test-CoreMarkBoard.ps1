param(
    [Parameter(Mandatory)][ValidatePattern('^COM[0-9]+$')][string]$PortName,
    [ValidateSet('V0', 'V1')][string]$Configuration = 'V0',
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$OutputDirectory
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$serial = $null
$raw = [System.Collections.Generic.List[byte]]::new()
try {
    $encoding = [System.Text.UTF8Encoding]::new($true)
    $output = [System.IO.Path]::GetFullPath($OutputDirectory)
    if (Test-Path -LiteralPath $output) { throw 'Choose a new output directory for each cold-programmed run.' }
    New-Item -ItemType Directory -Path $output | Out-Null
    $binaryPath = [System.IO.Path]::Combine($PSScriptRoot, 'project', 'cpu_paper', 'results', 'coremark-ablation-20260924T152600Z-68132642', 'firmware', $Configuration, 'firmware.bin')
    $expected = if ($Configuration -eq 'V0') {
        @{ sha = 'ba096213876766aa2c5a0aaa1ee055c34d3418912d3d50e67fd83c2c906aa118'; crc = 'bba62a9a'; size = 22864; cycles = '1793942498'; retired = '1649428429' }
    } else {
        @{ sha = 'd7440a2776e19c36db9869380fb4fd8b67bf90c55b4e3fd9d6bc3f69477c80b6'; crc = '2fe4a47a'; size = 22880; cycles = '1793507264'; retired = '1649775527' }
    }
    if ((Get-FileHash -LiteralPath $binaryPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.sha) { throw 'Firmware hash mismatch.' }
    $binary = [System.IO.File]::ReadAllBytes($binaryPath)
    $serial = [System.IO.Ports.SerialPort]::new($PortName, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
    $serial.Handshake = [System.IO.Ports.Handshake]::None
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.ReadTimeout = 1000
    $serial.WriteTimeout = 10000
    $serial.Open()
    function Read-Until {
        param([Parameter(Mandatory)][scriptblock]$Predicate, [int]$Seconds = 20)
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        while ($watch.Elapsed.TotalSeconds -lt $Seconds) {
            $available = $serial.BytesToRead
            if ($available -gt 0) {
                $buffer = [byte[]]::new($available)
                $received = $serial.Read($buffer, 0, $buffer.Length)
                for ($i = 0; $i -lt $received; $i++) { $raw.Add($buffer[$i]) }
            }
            $text = [System.Text.Encoding]::ASCII.GetString($raw.ToArray())
            if (& $Predicate $text) { return }
            Start-Sleep -Milliseconds 20
        }
        throw 'Timed out waiting for board UART response.'
    }
    $serial.Write('?')
    Read-Until -Predicate { param($text) $text.Contains("ZBOOT READY R`n") }
    $boundary = $raw.Count
    $header = [byte[]]::new(5)
    $header[0] = 82
    [BitConverter]::GetBytes([uint32]$binary.Length).CopyTo($header, 1)
    $serial.Write($header, 0, 5)
    $acknowledgements = 0
    for ($offset = 0; $offset -lt $binary.Length; $offset += 256) {
        $length = [Math]::Min(256, $binary.Length - $offset)
        $serial.Write($binary, $offset, $length)
        $acknowledgements++
        Read-Until -Predicate { param($text) ([regex]::Matches($text.Substring($boundary), 'K')).Count -ge $acknowledgements }
    }
    Read-Until -Predicate { param($text) $text.Substring($boundary) -match 'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n' }
    $transfer = [System.Text.Encoding]::ASCII.GetString($raw.ToArray()).Substring($boundary)
    $crc = [regex]::Match($transfer, 'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n')
    if ($crc.Groups[1].Value -ne $expected.crc -or [Convert]::ToInt32($crc.Groups[2].Value, 16) -ne $expected.size) { throw 'Board RAM CRC/size mismatch.' }
    if (([regex]::Matches($transfer.Substring(0, $crc.Index), 'K')).Count -ne ([Math]::Floor($binary.Length / 256) + 1)) { throw 'Loader acknowledgement count mismatch.' }
    Read-Until -Predicate { param($text) $text.Contains("ZGTC COREMARK READY send G; clock=153000000 Hz`n") } -Seconds 30
    $benchmarkBoundary = $raw.Count
    $serial.Write('G')
    Read-Until -Predicate { param($text) $text.Substring($benchmarkBoundary).Contains("ZGTC COREMARK FINISHED`n") } -Seconds 240
    $uart = [System.Text.Encoding]::ASCII.GetString($raw.ToArray()).Substring($benchmarkBoundary)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($output, 'uart.log'), $uart, $encoding)
    if (-not $uart.Contains($expected.cycles) -or -not $uart.Contains($expected.retired)) { throw 'Historical cycle/retirement reference not found; inspect captured UART.' }
    Write-Output 'UART transfer and reference-count checks completed. Compare complete output and CRC with archived observations before qualifying a new board run.'
} catch {
    Write-Error $_
    exit 1
} finally {
    if ($null -ne $serial) { if ($serial.IsOpen) { $serial.Close() }; $serial.Dispose() }
    if ($null -ne $output -and (Test-Path -LiteralPath $output -PathType Container)) {
        [System.IO.File]::WriteAllBytes([System.IO.Path]::Combine($output, 'serial.bin'), $raw.ToArray())
    }
}
