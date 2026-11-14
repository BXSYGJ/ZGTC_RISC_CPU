#Requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int] $Port = 8765,
    [ValidateNotNullOrEmpty()]
    [string] $PythonExe = 'python',
    [switch] $Foreground
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ownedProcess = $null

try {
    $serverPath = [System.IO.Path]::Combine($PSScriptRoot, 'server.py')
    if (-not [System.IO.File]::Exists($serverPath)) {
        throw "Server script missing: $serverPath"
    }
    $pythonCommand = Get-Command -Name $PythonExe -CommandType Application -ErrorAction Stop |
        Select-Object -First 1
    $pythonPath = $pythonCommand.Source

    # Detect an occupied port without contacting or stopping its current owner.
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $probe.Start()
    }
    finally {
        $probe.Stop()
    }

    if ($Foreground) {
        & $pythonPath -X utf8 -u $serverPath --port $Port
        if ($LASTEXITCODE -ne 0) {
            throw "Server exited with code $LASTEXITCODE"
        }
        exit 0
    }

    $runtimeRoot = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::Combine($PSScriptRoot, '..', '..', 'build', 'symphony'))
    [System.IO.Directory]::CreateDirectory($runtimeRoot) | Out-Null
    $sessionName = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $logPrefix = [System.IO.Path]::Combine($runtimeRoot, $sessionName)
    $stdoutPath = [System.IO.Path]::Combine($runtimeRoot, $sessionName + '.stdout.log')
    $stderrPath = [System.IO.Path]::Combine($runtimeRoot, $sessionName + '.stderr.log')
    $metadataPath = [System.IO.Path]::Combine($runtimeRoot, $sessionName + '.json')
    $arguments = @('-X', 'utf8', '-u', ('"' + $serverPath + '"'), '--port', $Port.ToString(),
        '--log-prefix', ('"' + $logPrefix + '"'))
    # Python owns its log streams; shell detachment avoids inherited capture handles.
    $ownedProcess = Start-Process -FilePath $pythonPath -ArgumentList $arguments `
        -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
    $url = 'http://127.0.0.1:' + $Port
    $deadline = [System.Diagnostics.Stopwatch]::StartNew()
    $ready = $false
    while ($deadline.Elapsed.TotalSeconds -lt 15) {
        $ownedProcess.Refresh()
        if ($ownedProcess.HasExited) {
            $details = if ([System.IO.File]::Exists($stderrPath)) {
                [System.IO.File]::ReadAllText($stderrPath, [System.Text.Encoding]::UTF8)
            } else {
                'The Python process did not create a log file.'
            }
            throw "Server exited during startup: $details"
        }
        try {
            $project = Invoke-RestMethod -Uri ($url + '/api/project') -TimeoutSec 1 -ErrorAction Stop
            if ($project.project.id -eq 'instrec-symphony') {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 100
        }
    }
    if (-not $ready) {
        throw "Server readiness timed out. Read $stderrPath"
    }
    $result = [ordered]@{
        pid = $ownedProcess.Id
        url = $url
        serial_opened = $false
        stdout = $stdoutPath
        stderr = $stderrPath
        metadata = $metadataPath
        python = $pythonPath
        started_at = [DateTimeOffset]::Now.ToString('o')
    }
    $json = $result | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($metadataPath, $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($true))
    Write-Output $json
}
catch {
    if ($null -ne $ownedProcess) {
        $ownedProcess.Refresh()
        if (-not $ownedProcess.HasExited) {
            Stop-Process -InputObject $ownedProcess -ErrorAction SilentlyContinue
        }
    }
    Write-Error $_
    exit 1
}
