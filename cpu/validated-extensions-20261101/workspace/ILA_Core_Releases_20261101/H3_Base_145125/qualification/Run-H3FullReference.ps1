param(
    [ValidateSet('H3_Base_145125', 'H3_Retained_145125')][string]$Release = 'H3_Base_145125',
    [ValidateRange(1800000000, 3000000000)][long]$CycleLimit = 2100000000,
    [ValidateRange(1800, 10800)][int]$TimeoutSeconds = 7200
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $workspace=[System.IO.Path]::Combine('D:','AAAFPGA')
    $taskRoot=[System.IO.Path]::Combine($workspace,'ILA_Core_Releases_20261101')
    $qualification=[System.IO.Path]::Combine($taskRoot,$Release,'qualification')
    $fixture=[System.IO.Path]::Combine($qualification,'dynamic','MODIFIED')
    $reference=[System.IO.Path]::Combine($qualification,'reference')
    $root=[System.IO.Path]::Combine($qualification,'full_reference')
    $utf8Bom=[System.Text.UTF8Encoding]::new($true)
    function Save-Json([string]$Path,[object]$Value){[System.IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 20),$utf8Bom)}
    function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
    function LinuxPath([string]$Path){$full=[System.IO.Path]::GetFullPath($Path);if($full -notmatch '^[A-Za-z]:'){throw 'Expected local drive path.'};'/mnt/'+$full.Substring(0,1).ToLowerInvariant()+'/'+$full.Substring(3).Replace([System.IO.Path]::DirectorySeparatorChar,'/')}
    if(Test-Path -LiteralPath ([System.IO.Path]::Combine($root,'NATIVE_PROCESS.json'))){throw 'Full reference run already started; inspect its process and evidence.'}
    $exe=[System.IO.Path]::Combine($fixture,'objects','Vrv32_observed_soc')
    if(-not(Test-Path -LiteralPath $exe -PathType Leaf)){throw 'Validated modified simulator missing.'}
    $identity=Get-Content -LiteralPath ([System.IO.Path]::Combine($fixture,'SOURCE_IDENTITY.json')) -Raw -Encoding utf8|ConvertFrom-Json
    $baseline=Get-Content -LiteralPath ([System.IO.Path]::Combine($fixture,'RESULT.json')) -Raw -Encoding utf8|ConvertFrom-Json
    if(-not $baseline.baseline_uart_equal -or -not $baseline.baseline_cycles_trace_and_42_probes_equal){throw 'Modified fixture has not passed dynamic equality qualification.'}
    [void][System.IO.Directory]::CreateDirectory($root)
    $firmware=[System.IO.Path]::Combine($root,'firmware.hex')
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($fixture,'firmware.hex')) -Destination $firmware
    if((Sha $firmware) -cne $identity.firmware_sha256 -or (Sha $firmware) -cne (Sha ([System.IO.Path]::Combine($reference,'firmware.hex')))){throw 'Full run firmware differs from frozen V0.'}
    $uart=[System.IO.Path]::Combine($root,'uart.log')
    $stdout=[System.IO.Path]::Combine($root,'run.stdout.log')
    $stderr=[System.IO.Path]::Combine($root,'run.stderr.log')
    $arguments=@('--cd',(LinuxPath $root),'--exec',(LinuxPath $exe),(LinuxPath $uart),$CycleLimit.ToString([System.Globalization.CultureInfo]::InvariantCulture))
    $env:WSL_UTF8='1'
    $started=[datetime]::UtcNow
    $process=Start-Process -FilePath 'wsl.exe' -ArgumentList $arguments -PassThru -WindowStyle Hidden -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $receipt=[ordered]@{schema='h3-full-reference-native-run/v1';release=$Release;origin='LOCAL RTL SIMULATION';executable='wsl.exe';arguments=$arguments;native_simulator=$exe;native_simulator_sha256=Sha $exe;source_identity=[System.IO.Path]::Combine($fixture,'SOURCE_IDENTITY.json');source_identity_sha256=Sha ([System.IO.Path]::Combine($fixture,'SOURCE_IDENTITY.json'));firmware_sha256=Sha $firmware;working_directory=$root;pid=$process.Id;started_utc=$started.ToString('o');actual_exit_code=$null;status='running';cycle_limit=$CycleLimit;reference_uart=[System.IO.Path]::Combine($reference,'uart.log');reference_uart_sha256=Sha ([System.IO.Path]::Combine($reference,'uart.log'));stdout=$stdout;stderr=$stderr}
    $receiptPath=[System.IO.Path]::Combine($root,'NATIVE_PROCESS.json')
    Save-Json $receiptPath $receipt
    Write-Output ('FULL_REFERENCE_STARTED release='+$Release+' pid='+$process.Id+' cycle_limit='+$CycleLimit+' simulator='+$exe)
    $lastProgress=[datetime]::UtcNow
    while(-not $process.WaitForExit(15000)){
        $now=[datetime]::UtcNow
        if(($now-$started).TotalSeconds -gt $TimeoutSeconds){$process.Kill($true);$process.WaitForExit();$receipt['status']='timeout';$receipt['actual_exit_code']=$process.ExitCode;Save-Json $receiptPath $receipt;throw 'Full reference simulation exceeded its recorded timeout.'}
        if(($now-$lastProgress).TotalSeconds -ge 60){Write-Output ('FULL_REFERENCE_RUNNING release='+$Release+' elapsed_seconds='+[int]($now-$started).TotalSeconds);$lastProgress=$now}
    }
    $process.WaitForExit()
    $receipt['actual_exit_code']=$process.ExitCode
    $receipt['finished_utc']=[datetime]::UtcNow.ToString('o')
    $receipt['elapsed_seconds']=([datetime]::UtcNow-$started).TotalSeconds
    $receipt['status']='finished'
    Save-Json $receiptPath $receipt
    $outText=[System.IO.File]::ReadAllText($stdout)
    if($process.ExitCode -ne 0){throw ('Full native simulator exit='+$process.ExitCode)}
    if($outText -notmatch 'PASS RTL CoreMark smoke' -or $outText -notmatch 'ZGTC COREMARK FINISHED' -or $outText -match 'PARTIAL_WINDOW_PASS'){throw 'Full native simulator did not finish the benchmark.'}
    $actualUART=[System.IO.File]::ReadAllText($uart)
    $referenceUART=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($reference,'uart.log'))
    if($actualUART -cne $referenceUART -or (Sha $uart) -cne $receipt.reference_uart_sha256){throw 'Full native UART differs from the frozen reference.'}
    $counters=[regex]::Match($actualUART,'ZGTC cycles_hex=([0-9a-fA-F]+) retired_hex=([0-9a-fA-F]+) clock_hz=(\d+)')
    if(-not $counters.Success){throw 'Full native UART counters missing.'}
    $result=[ordered]@{schema='h3-full-reference-comparison/v1';release=$Release;origin='LOCAL RTL SIMULATION';completed_6000_iterations=$true;native_exit_code=$process.ExitCode;exact_reference_uart_equal=$true;uart=$uart;uart_sha256=Sha $uart;reference_uart_sha256=$receipt.reference_uart_sha256;cycles_hex=$counters.Groups[1].Value;cycles=[Convert]::ToUInt64($counters.Groups[1].Value,16);retired_hex=$counters.Groups[2].Value;retired=[Convert]::ToUInt64($counters.Groups[2].Value,16);clock_hz=[long]$counters.Groups[3].Value;firmware_sha256=Sha $firmware;all_crc_fields_equal_by_exact_uart=$true;literal_stdout=$outText;run_receipt=$receiptPath;hardware_validated=$false;comparison_utc=[datetime]::UtcNow.ToString('o')}
    $resultPath=[System.IO.Path]::Combine($root,'RESULT.json')
    Save-Json $resultPath $result
    foreach($path in @($receiptPath,$resultPath,$uart,$stdout,$stderr)){$null=[System.IO.File]::ReadAllText($path)}
    Write-Output ('FULL_REFERENCE_PASS release='+$Release+' cycles='+$result.cycles+' retired='+$result.retired+' exact_uart_crc_counters_equal=true native_exit=0')
    Write-Output ('FULL_REFERENCE_RESULT='+$resultPath)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
