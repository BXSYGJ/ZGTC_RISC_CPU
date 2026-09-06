param([ValidateRange(0,1)][int]$FastICacheHit = 0, [ValidateRange(0,1)][int]$LoadUseBubble = 0)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
    $toolchain=Get-RiscvToolchain
    $project=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $revision='2ebecad997fa58cd9e5724340ba75aa4b59bd1d0'
    $expectedHash='1B6BBCA3A60B81FD3B94FA5DB6497D48918944C80C74E5BCF39BBD5DDC63C483'
    $archive=[System.IO.Path]::Combine($project,'build',"riscv-tests-$revision.tar.gz")
    $url="https://codeload.github.com/riscv-software-src/riscv-tests/tar.gz/$revision"
    if(-not (Test-Path -LiteralPath $archive -PathType Leaf)) { Invoke-WebRequest -Uri $url -OutFile $archive -TimeoutSec 120 }
    if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Pinned upstream archive hash mismatch.' }
    $runName=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+([guid]::NewGuid().ToString('N').Substring(0,8))
    $build=[System.IO.Path]::Combine($project,'build','isa',$runName)
    $source=[System.IO.Path]::Combine($build,'source')
    [void](New-Item -ItemType Directory -Path $source)
    function Convert-LinuxPath([string]$Path) {
        $converted=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $Path).Trim()
        if($LASTEXITCODE) { throw 'WSL path conversion failed.' }
        return $converted
    }
    $linuxProject=Convert-LinuxPath $project
    $linuxBuild=Convert-LinuxPath $build
    $linuxSource=Convert-LinuxPath $source
    $linuxArchive=Convert-LinuxPath $archive
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/tar -xf $linuxArchive -C $linuxSource --strip-components=1
    if($LASTEXITCODE) { throw 'Upstream extraction failed.' }
    $manifest=[ordered]@{Revision=$revision;ArchiveSha256=$expectedHash;SourceUrl=$url;Build=$build;Toolchain=$toolchain;StartedUtc=[datetime]::UtcNow.ToString('o')}
    $manifest['LoadUseBubble'] = $LoadUseBubble
    $manifest['FastICacheHit'] = $FastICacheHit
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ([System.IO.Path]::Combine($build,'run.json')) -Encoding utf8BOM
    $linuxRunner=[System.IO.Path]::Combine($linuxProject,'scripts','run_isa.py').Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    $runLog=[System.IO.Path]::Combine($build,'run.log')
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $linuxRunner --project $linuxProject --source $linuxSource --build $linuxBuild --tool-prefix $toolchain.Prefix --load-use-bubble $LoadUseBubble --fast-icache-hit $FastICacheHit 2>&1 | ForEach-Object {
        $_ | Out-File -LiteralPath $runLog -Append -Encoding utf8BOM
        Write-Output $_
    }
    if($LASTEXITCODE) { throw "External ISA tests failed; inspect $build" }
    $results=Get-Content -LiteralPath ([System.IO.Path]::Combine($build,'results.json')) -Raw | ConvertFrom-Json
    if($results.status -ne 'passed') { throw 'External ISA result manifest is not passed.' }
    $manifest['Result']=[System.IO.Path]::Combine($build,'results.json')
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','isa-latest.json')) -Encoding utf8BOM
    Write-Output "PASS external ISA report: $build"
} catch {
    Write-Error $_
    exit 1
}
