param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$BuildDirectory,
    [ValidateRange(1900000000,3000000000)][long]$CycleBudget=2100000000,
    [string]$ExistingRunDirectory
)
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $bom=[System.Text.UTF8Encoding]::new($true)
    function Save-Json([string]$Path,$Value){[System.IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 24),$bom)}
    function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
    function Linux([string]$Path){$p=[System.IO.Path]::GetFullPath($Path);if($p -notmatch '^[A-Za-z]:'){throw 'Expected local drive path.'};'/mnt/'+$p.Substring(0,1).ToLowerInvariant()+'/'+$p.Substring(3).Replace([System.IO.Path]::DirectorySeparatorChar,'/')}
    function Run-Wsl([string[]]$Arguments,[string]$Prefix,[int]$TimeoutSeconds){
        $info=[System.Diagnostics.ProcessStartInfo]::new('wsl.exe');$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.StandardOutputEncoding=[Text.Encoding]::UTF8;$info.StandardErrorEncoding=[Text.Encoding]::UTF8
        foreach($argument in $Arguments){$info.ArgumentList.Add($argument)}
        $started=[datetime]::UtcNow;$process=[System.Diagnostics.Process]::Start($info);$outTask=$process.StandardOutput.ReadToEndAsync();$errTask=$process.StandardError.ReadToEndAsync()
        Save-Json ($Prefix+'.process.json') ([ordered]@{pid=$process.Id;executable='wsl.exe';arguments=$Arguments;started_utc=$started.ToString('o');status='running'})
        $watch=[Diagnostics.Stopwatch]::StartNew()
        while(-not $process.WaitForExit(15000)){Write-Host ('FULL_RUN_PROGRESS elapsed_seconds='+[int]$watch.Elapsed.TotalSeconds);if($watch.Elapsed.TotalSeconds -gt $TimeoutSeconds){throw 'Full simulation monitoring timeout; the recorded owned process remains available for inspection.'}}
        $stdout=$outTask.GetAwaiter().GetResult();$stderr=$errTask.GetAwaiter().GetResult();[System.IO.File]::WriteAllText(($Prefix+'.stdout.log'),$stdout,$bom);[System.IO.File]::WriteAllText(($Prefix+'.stderr.log'),$stderr,$bom)
        Save-Json ($Prefix+'.command.json') ([ordered]@{executable='wsl.exe';arguments=$Arguments;exit_code=$process.ExitCode;started_utc=$started.ToString('o');finished_utc=[datetime]::UtcNow.ToString('o');stdout=$Prefix+'.stdout.log';stderr=$Prefix+'.stderr.log'})
        if($process.ExitCode -ne 0){throw ('Full simulation command failed: '+$Prefix+' exit='+$process.ExitCode)}
        return $stdout
    }
    $task=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..','..'))
    $releaseRoot=[System.IO.Path]::Combine($task,'Original_155250')
    $build=[System.IO.Path]::GetFullPath($BuildDirectory)
    if(-not $build.StartsWith($releaseRoot+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Build directory must belong to the isolated Original release.'}
    $frozen=[System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($task),'Current_Paper_and_Sub7000_Core_Releases_20261012','cores','Original_155250')
    $recipe=Get-Content -LiteralPath ([System.IO.Path]::Combine($frozen,'recipe.json')) -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    $run=if([string]::IsNullOrWhiteSpace($ExistingRunDirectory)){[System.IO.Path]::Combine($PSScriptRoot,'full-runs',([datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)))}else{[System.IO.Path]::GetFullPath($ExistingRunDirectory)}
    $runPrefix=[System.IO.Path]::Combine($PSScriptRoot,'full-runs')+[System.IO.Path]::DirectorySeparatorChar
    if(-not $run.StartsWith($runPrefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Full simulation run must belong to its qualification directory.'}
    if([string]::IsNullOrWhiteSpace($ExistingRunDirectory)) {
    $inputs=[System.IO.Path]::Combine($run,'inputs');[void][System.IO.Directory]::CreateDirectory($inputs)
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($build,'inputs','rtl')) -Destination ([System.IO.Path]::Combine($inputs,'rtl')) -Recurse
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($frozen,'simulation','inputs','sim')) -Destination ([System.IO.Path]::Combine($inputs,'sim')) -Recurse
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($build,'inputs','firmware.hex')) -Destination ([System.IO.Path]::Combine($run,'firmware.hex'))
    if((Sha ([System.IO.Path]::Combine($run,'firmware.hex'))) -ne $recipe.roles.V0.firmware_sha256){throw 'Full-run firmware hash differs from the unchanged frozen V0.'}
    $hashes=[ordered]@{}
    foreach($file in Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($inputs,'rtl')) -File){$reference=[System.IO.Path]::Combine($frozen,'physical','V0','inputs','rtl',$file.Name);if((Sha $reference) -ne (Sha $file.FullName)){throw ('Functional RTL differs from frozen input: '+$file.Name)};$hashes[$file.Name]=Sha $file.FullName}
    foreach($name in @('rv32_observed_soc.sv','driver.cpp')){$file=[System.IO.Path]::Combine($inputs,'sim',$name);$reference=[System.IO.Path]::Combine($frozen,'simulation','inputs','sim',$name);if((Sha $file) -ne (Sha $reference)){throw 'Frozen simulator driver or observer differs.'};$hashes[$name]=Sha $file}
    Save-Json ([System.IO.Path]::Combine($run,'SOURCE_IDENTITY.json')) ([ordered]@{origin='LOCAL RTL SIMULATION';build_directory=$build;functional_rtl_edits=0;driver_edits=0;hashes=$hashes;firmware_sha256=Sha ([System.IO.Path]::Combine($run,'firmware.hex'));iterations=6000;configured_fpga_clock_hz=155250000;simulation_uart_clock_hz=3200;simulation_uart_baud=100;cycle_budget=$CycleBudget})
    $arguments=@($recipe.simulation.argv|ForEach-Object{$_.Replace('{RELEASE}/simulation/inputs',(Linux $inputs)).Replace('{OUTPUT}',(Linux $run))});$jobs=[array]::IndexOf($arguments,'-j');$arguments[$jobs+1]='1';$env:WSL_UTF8='1'
    Write-Output ('FULL_SIMULATION_DIRECTORY='+$run)
    $null=Run-Wsl (@('--cd','/tmp','--exec',$recipe.simulation.tool_original)+$arguments) ([System.IO.Path]::Combine($run,'compile')) 900
    $uart=[System.IO.Path]::Combine($run,'uart.log');$executable=[System.IO.Path]::Combine($run,'objects','Vrv32_observed_soc')
    $output=Run-Wsl @('--cd',(Linux $run),'--exec',(Linux $executable),(Linux $uart),$CycleBudget.ToString([Globalization.CultureInfo]::InvariantCulture)) ([System.IO.Path]::Combine($run,'simulate')) 7200
    } else {
        $identity=Get-Content -LiteralPath ([System.IO.Path]::Combine($run,'SOURCE_IDENTITY.json')) -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
        $command=Get-Content -LiteralPath ([System.IO.Path]::Combine($run,'simulate.command.json')) -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
        if($command.exit_code -ne 0 -or $identity.build_directory -ne $build){throw 'Existing full simulation identity or exit status differs.'}
        foreach($name in $identity.hashes.Keys){$category=if($name -in @('driver.cpp','rv32_observed_soc.sv')){'sim'}else{'rtl'};if((Sha ([System.IO.Path]::Combine($run,'inputs',$category,$name))) -ne $identity.hashes[$name]){throw ('Existing full simulation source changed: '+$name)}}
        $uart=[System.IO.Path]::Combine($run,'uart.log');$output=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($run,'simulate.stdout.log'))
    }
    $uartText=[System.IO.File]::ReadAllText($uart);$referenceUart=[System.IO.Path]::Combine($frozen,'firmware','V0','uart.log')
    if($output -notmatch 'PASS RTL CoreMark smoke' -or $uartText -notmatch 'ZGTC COREMARK FINISHED'){throw 'Full simulation did not reach verified CoreMark completion.'}
    $actual=[regex]::Matches($uartText,'ZGTC cycles_hex=([0-9a-fA-F]{16}) retired_hex=([0-9a-fA-F]{16})')
    $expected=[regex]::Matches([System.IO.File]::ReadAllText($referenceUart),'ZGTC cycles_hex=([0-9a-fA-F]{16}) retired_hex=([0-9a-fA-F]{16})')
    if($actual.Count -ne 1 -or $expected.Count -ne 1 -or $actual[0].Value -cne $expected[0].Value){throw 'Full-run cycle/retired values differ from the frozen reference.'}
    if((Sha $uart) -ne (Sha $referenceUart)){throw 'Full-run UART bytes differ from the frozen reference.'}
    $result=[ordered]@{origin='LOCAL RTL SIMULATION';complete_coremark_run=$true;iterations=6000;firmware_sha256=Sha ([System.IO.Path]::Combine($run,'firmware.hex'));uart_sha256=Sha $uart;reference_uart_sha256=Sha $referenceUart;uart_byte_identical=$true;cycle_count=[Convert]::ToUInt64($actual[0].Groups[1].Value,16);retired_count=[Convert]::ToUInt64($actual[0].Groups[2].Value,16);baseline_cycles_and_retired_equal=$true;hardware_validated=$false;exit_code=0;run_directory=$run;exact_stdout=$output;completed_utc=[datetime]::UtcNow.ToString('o')}
    $resultPath=[System.IO.Path]::Combine($run,'RESULT.json');Save-Json $resultPath $result
    [void][System.IO.File]::ReadAllText($resultPath);Write-Output ($result|ConvertTo-Json -Depth 24);exit 0
} catch {Write-Error -Message $_.Exception.Message -ErrorAction Continue;exit 1}
