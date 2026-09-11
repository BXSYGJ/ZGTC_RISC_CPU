param([Parameter(Mandatory)][ValidatePattern('^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$')][string]$SourceRun,
      [ValidateRange(0,2147483647)][int]$PlacementSeed=2)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $root=[IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    $stage=[IO.Path]::Combine($root,'build','full-resource-opt-timer-keep-stage')
    $source=[IO.Path]::Combine($stage,'build','pds',$SourceRun)
    if(@(Get-Process -Name pds_shell,cdt_ins -ErrorAction SilentlyContinue).Count){throw 'A vendor process is live; inspect it first'}
    $name=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+([guid]::NewGuid().ToString('N').Substring(0,8))
    $build=[IO.Path]::Combine($stage,'build','ila',$name)
    [void](New-Item -ItemType Directory -Path $build)
    $auditor=[IO.Path]::Combine($PSScriptRoot,'audit_ila.py')
    $linux=@()
    foreach($path in @($auditor,$source,$build)){
        if($path -match '[{}"$;\r\n]'){throw 'Unsafe generated Tcl path'}
        $linux+=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $path).Trim()
        if($LASTEXITCODE){throw 'WSL path conversion failed'}
    }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 @linux --mode prepare *> ([IO.Path]::Combine($build,'prepare.log'))
    if($LASTEXITCODE){throw 'Full source/firmware/parameter audit failed'}
    $adf=[IO.Path]::Combine($build,'source.adf')
    $netlist=[IO.Path]::Combine($build,'netlist.v')
    Copy-Item -LiteralPath ([IO.Path]::Combine($source,'synthesize','pds_soc_top_syn.adf')) -Destination $adf
    Copy-Item -LiteralPath ([IO.Path]::Combine($source,'synthesize','pds_soc_top_syn.vm')) -Destination $netlist
    Copy-Item -LiteralPath ([IO.Path]::Combine($source,'firmware.hex')) -Destination ([IO.Path]::Combine($build,'firmware.hex'))
    foreach($constraint in @('board.fdc','uart_remotelab.fdc')){Copy-Item -LiteralPath ([IO.Path]::Combine($source,'source','constraints',$constraint)) -Destination ([IO.Path]::Combine($build,$constraint))}
    $utf8=[Text.UTF8Encoding]::new($false)
    $fic=[IO.Path]::Combine($build,'cpu.fic')
    $template=[IO.File]::ReadAllText([IO.Path]::Combine($root,'scripts','cpu_ila_regfilefanout157500_minimal.fic.in'))
    [IO.File]::WriteAllText($fic,$template.Replace('__SOURCE_ADF__',$adf.Replace([IO.Path]::DirectorySeparatorChar,'/')),$utf8)
    $verify=[IO.Path]::Combine($build,'verify.tcl')
    $ficTcl=$fic.Replace([IO.Path]::DirectorySeparatorChar,'/')
    [IO.File]::WriteAllLines($verify,@("ins_open {$ficTcl}",'ins_core_info -core 0','ins_core_info -core 0 -trig 0 -unit 0','ins_save','exit'),$utf8)
    $env:PANGO_LICENSE_FILE=[Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE','User')
    if([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)){throw 'Missing PDS license configuration'}
    $vendor=[IO.Path]::Combine('D:/','PDS_2022.2-SP6.4','bin')
    $verifyArgument=$verify.Replace([IO.Path]::DirectorySeparatorChar,'/')
    $process=Start-Process -FilePath ([IO.Path]::Combine($vendor,'cdt_ins.exe')) -ArgumentList @('-device','PG2L200H','-package','FBB676','-speedgrade','-6','-file',('"'+$verifyArgument+'"')) -PassThru -WindowStyle Hidden -WorkingDirectory $build -RedirectStandardOutput ([IO.Path]::Combine($build,'verify.stdout.txt')) -RedirectStandardError ([IO.Path]::Combine($build,'verify.stderr.txt'))
    Write-Output ('Named ILA mapping PID='+$process.Id+' build='+$build)
    $process.WaitForExit()
    if($process.ExitCode){throw 'Inserter process failed'}
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 @linux --mode mapping *> ([IO.Path]::Combine($build,'mapping.log'))
    if($LASTEXITCODE){throw '42 data/33 trigger mapping audit failed'}
    $placement=[ordered]@{Schema=1;Seed=$PlacementSeed;Command=('pnr -gplace_seed '+$PlacementSeed)}
    $placement | ConvertTo-Json | Set-Content -LiteralPath ([IO.Path]::Combine($build,'placement.json')) -Encoding utf8BOM
    $board=[IO.Path]::Combine($build,'board.fdc')
    $uart=[IO.Path]::Combine($build,'uart_remotelab.fdc')
    $commands=@("add_design {$netlist}","add_constraint {$board}","add_constraint {$uart}","add_fic {$fic}",'set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676','compile -system_verilog -top_module pds_soc_top',"dev_map -input_db_file {$adf}",$placement.Command,'report_timing','gen_bit_stream') | ForEach-Object {$_.Replace([IO.Path]::DirectorySeparatorChar,'/')}
    $script=[IO.Path]::Combine($build,'build.tcl')
    [IO.File]::WriteAllLines($script,$commands,$utf8)
    $stdout=[IO.Path]::Combine($build,'pds.stdout.log')
    $stderr=[IO.Path]::Combine($build,'pds.stderr.log')
    $process=Start-Process -FilePath ([IO.Path]::Combine($vendor,'pds_shell.exe')) -ArgumentList @('-file',('"'+$script+'"'),'-work_dir',('"'+$build+'"'),'-project_name','cpu_ila') -PassThru -WindowStyle Hidden -WorkingDirectory $build -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-Output ('Complete inserted PDS PID='+$process.Id+' build='+$build)
    $process.WaitForExit()
    $logs=[IO.File]::ReadAllText($stdout)+[IO.File]::ReadAllText($stderr)
    if($process.ExitCode -or $logs -match '(?m)^E:'){throw 'Inserted PDS process failed'}
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 @linux --mode result *> ([IO.Path]::Combine($build,'result.log'))
    if($LASTEXITCODE){throw 'Inserted artifact audit failed'}
    Get-Content -LiteralPath ([IO.Path]::Combine($build,'result.log')) -Encoding utf8
    $qualification=Get-Content -LiteralPath ([IO.Path]::Combine($build,'result-qualification.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    if($qualification.candidate_rejected){throw ('Complete-version candidate rejected: '+($qualification.rejection_reasons -join '; '))}
} catch {Write-Error $_; exit 1}
