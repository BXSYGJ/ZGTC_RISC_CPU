param([ValidateRange(1,8)][int]$Jobs=8,[string]$InstallRoot='')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Set-StrictMode -Version Latest
try {
    $project=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $downloads=[System.IO.Path]::Combine($project,'build','toolchain-downloads')
    [void](New-Item -ItemType Directory -Path $downloads -Force)
    $sources=Get-Content -LiteralPath ([System.IO.Path]::Combine($PSScriptRoot,'toolchain_sources.json')) -Raw | ConvertFrom-Json
    foreach($source in @($sources.binutils,$sources.gcc)) {
        $uri=[uri]$source.url
        if($uri.Scheme -ne 'https' -or $uri.Host -notin @('gcc.gnu.org','ftp.gnu.org') -or $source.filename -notmatch '^[a-z0-9][a-z0-9.-]*\.tar\.xz$' -or $source.sha512 -notmatch '^[0-9A-Fa-f]{128}$') { throw 'Invalid pinned source metadata.' }
        $archive=[System.IO.Path]::Combine($downloads,$source.filename)
        if(-not (Test-Path -LiteralPath $archive -PathType Leaf)) { Invoke-WebRequest -Uri $uri -OutFile $archive -TimeoutSec 240 }
        if((Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash -ne $source.sha512) { throw "Source checksum mismatch: $archive" }
    }
    $linuxHome=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/printenv HOME).Trim()
    if($LASTEXITCODE -or $linuxHome -notmatch '^/home/[A-Za-z0-9._-]+$') { throw 'Expected a regular WSL user home.' }
    if([string]::IsNullOrWhiteSpace($InstallRoot)) { $InstallRoot=[System.IO.Path]::Combine($linuxHome,'.local','zgtc-riscv32-10.2.0').Replace([System.IO.Path]::DirectorySeparatorChar,'/') }
    if(-not $InstallRoot.StartsWith($linuxHome+'/') -or $InstallRoot -notmatch '^/[A-Za-z0-9/._-]+$' -or ($InstallRoot.Split('/') -contains '..')) { throw 'InstallRoot must be an ASCII path inside the current WSL home without parent traversal.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/test -e $InstallRoot
    if($LASTEXITCODE -eq 0) { throw 'Installation prefix already exists; choose another InstallRoot. Existing tools are never overwritten.' }
    $runName=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+([guid]::NewGuid().ToString('N').Substring(0,8))
    $logs=[System.IO.Path]::Combine($project,'build','toolchain',$runName)
    [void](New-Item -ItemType Directory -Path $logs)
    $work=[System.IO.Path]::Combine($linuxHome,'.cache','zgtc-toolchain',$runName).Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    $sourceDirectory=[System.IO.Path]::Combine($work,'source').Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    $binutilsBuild=[System.IO.Path]::Combine($work,'binutils-build').Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    $gccBuild=[System.IO.Path]::Combine($work,'gcc-build').Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/mkdir -p $sourceDirectory $binutilsBuild $gccBuild
    if($LASTEXITCODE) { throw 'Cannot create isolated Linux build directories.' }
    $run=[ordered]@{RunName=$runName;WorkRoot=$work;InstallRoot=$InstallRoot;LogDirectory=$logs;Target='riscv32-unknown-elf';Arch='rv32i';Abi='ilp32';StartedUtc=[datetime]::UtcNow.ToString('o');Sources=$sources}
    $run | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ([System.IO.Path]::Combine($logs,'run.json')) -Encoding utf8BOM
    function Invoke-WslStage {
        param([string]$Name,[string]$Directory,[string]$Executable,[string[]]$CommandArguments)
        $log=[System.IO.Path]::Combine($logs,"$Name.log")
        Write-Output "START $Name; log=$log"
        & wsl.exe --distribution Ubuntu-22.04 --cd $Directory --exec $Executable @CommandArguments 2>&1 | Out-File -LiteralPath $log -Encoding utf8BOM
        if($LASTEXITCODE) { throw "Stage $Name failed with exit $LASTEXITCODE; inspect $log" }
        Write-Output "PASS $Name"
    }
    foreach($source in @($sources.binutils,$sources.gcc)) {
        $archive=[System.IO.Path]::Combine($downloads,$source.filename)
        $linuxArchive=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $archive).Trim()
        if($LASTEXITCODE) { throw 'Archive path conversion failed.' }
        Invoke-WslStage -Name ('extract-'+$source.version) -Directory $work -Executable '/usr/bin/tar' -CommandArguments @('-xf',$linuxArchive,'-C',$sourceDirectory)
    }
    $binutilsSource=[System.IO.Path]::Combine($sourceDirectory,'binutils-2.35','configure').Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    $gccSource=[System.IO.Path]::Combine($sourceDirectory,'gcc-10.2.0','configure').Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    $toolPrefix=[System.IO.Path]::Combine($InstallRoot,'bin','riscv32-unknown-elf-').Replace([System.IO.Path]::DirectorySeparatorChar,'/')
    $environmentPath="PATH=$InstallRoot/bin:/usr/bin:/bin"
    $binutilsArguments=@("--prefix=$InstallRoot",'--target=riscv32-unknown-elf','--disable-nls','--disable-werror')
    Invoke-WslStage -Name 'configure-binutils' -Directory $binutilsBuild -Executable $binutilsSource -CommandArguments $binutilsArguments
    Invoke-WslStage -Name 'build-binutils' -Directory $binutilsBuild -Executable '/usr/bin/make' -CommandArguments @("-j$Jobs")
    Invoke-WslStage -Name 'install-binutils' -Directory $binutilsBuild -Executable '/usr/bin/make' -CommandArguments @('install')
    $gccArguments=@("--prefix=$InstallRoot",'--target=riscv32-unknown-elf','--with-arch=rv32i','--with-abi=ilp32',
        '--enable-languages=c','--disable-bootstrap','--disable-multilib','--disable-nls','--disable-shared','--disable-threads',
        '--with-newlib','--without-headers','--disable-libssp','--disable-libquadmath','--disable-libgomp',
        '--disable-libatomic','--disable-libstdcxx','--disable-fixinc','--with-system-zlib','--enable-checking=yes',
        '--with-gnu-as','--with-gnu-ld',"--with-as=${toolPrefix}as","--with-ld=${toolPrefix}ld",'CFLAGS_FOR_TARGET=-Os -mcmodel=medany')
    Invoke-WslStage -Name 'configure-gcc' -Directory $gccBuild -Executable '/usr/bin/env' -CommandArguments (@($environmentPath,$gccSource)+$gccArguments)
    Invoke-WslStage -Name 'build-gcc' -Directory $gccBuild -Executable '/usr/bin/env' -CommandArguments @($environmentPath,'/usr/bin/make',"-j$Jobs",'all-gcc')
    Invoke-WslStage -Name 'install-gcc' -Directory $gccBuild -Executable '/usr/bin/env' -CommandArguments @($environmentPath,'/usr/bin/make','install-gcc')
    Invoke-WslStage -Name 'build-libgcc' -Directory $gccBuild -Executable '/usr/bin/env' -CommandArguments @($environmentPath,'/usr/bin/make',"-j$Jobs",'all-target-libgcc')
    Invoke-WslStage -Name 'install-libgcc' -Directory $gccBuild -Executable '/usr/bin/env' -CommandArguments @($environmentPath,'/usr/bin/make','install-target-libgcc')
    $target=(& wsl.exe --distribution Ubuntu-22.04 --exec "${toolPrefix}gcc" -dumpmachine).Trim()
    if($LASTEXITCODE -or $target -ne 'riscv32-unknown-elf') { throw 'Installed compiler has the wrong target.' }
    $version=(& wsl.exe --distribution Ubuntu-22.04 --exec "${toolPrefix}gcc" -dumpfullversion).Trim()
    if($LASTEXITCODE -or $version -ne '10.2.0') { throw 'Installed compiler has the wrong version.' }
    $library=(& wsl.exe --distribution Ubuntu-22.04 --exec "${toolPrefix}gcc" -print-libgcc-file-name).Trim()
    if($LASTEXITCODE) { throw 'Cannot locate target libgcc.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/test -s $library
    if($LASTEXITCODE) { throw 'Target libgcc is missing.' }
    Invoke-WslStage -Name 'compiler-identification' -Directory $gccBuild -Executable ("${toolPrefix}gcc") -CommandArguments @('-v')
    Invoke-WslStage -Name 'libgcc-object-formats' -Directory $gccBuild -Executable ("${toolPrefix}objdump") -CommandArguments @('-f',$library)
    $formats=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($logs,'libgcc-object-formats.log'))
    if($formats -notmatch 'elf32-littleriscv' -or $formats -match 'elf64') { throw 'Target libgcc archive is not RV32-only.' }
    $run['ToolPrefix']=$toolPrefix
    $run['CompilerVersion']=$version
    $run['Libgcc']=$library
    $run['BinutilsConfigure']=$binutilsArguments
    $run['GccConfigure']=$gccArguments
    $run['CompletedUtc']=[datetime]::UtcNow.ToString('o')
    $run | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ([System.IO.Path]::Combine($logs,'installed.json')) -Encoding utf8BOM
    $run | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','riscv32-toolchain.json')) -Encoding utf8BOM
    Write-Output "PASS installed true $target GCC $version; prefix=$toolPrefix"
} catch {
    Write-Error $_
    exit 1
}
