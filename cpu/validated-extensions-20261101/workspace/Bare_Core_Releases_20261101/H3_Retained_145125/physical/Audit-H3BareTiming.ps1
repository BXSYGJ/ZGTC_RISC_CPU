param(
    [ValidateSet('H3_Base_145125', 'H3_Retained_145125')][string]$Release = 'H3_Base_145125',
    [Parameter(Mandatory)][ValidateLength(1, 500)][string]$BuildDirectory,
    [ValidateRange(0.01,1.0)][double]$ExpectedEffectiveSetupUncertaintyNs=0.200
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $taskRoot = [System.IO.Path]::Combine('D:', 'AAAFPGA', 'Bare_Core_Releases_20261101')
    $build = [System.IO.Path]::GetFullPath($BuildDirectory)
    $prefix = [System.IO.Path]::Combine($taskRoot, $Release, 'physical', 'builds') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $build.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Timing audit target must be an isolated build of the specified release.' }
    $implementation = [System.IO.Path]::Combine($build, 'implementation')
    $reportPath = [System.IO.Path]::Combine($implementation, 'report_timing', 'bare_core_scan_top.rtr')
    $timing = [System.IO.File]::ReadAllText($reportPath)
    $log = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($implementation, 'run.log'))
    $invariant = [System.Globalization.CultureInfo]::InvariantCulture
    function Number([string]$Text) { [double]::Parse($Text,$invariant) }
    if ($timing -notmatch 'Timing analysis mode\s*:\s*multi corner') { throw 'Final timing report is not multi corner.' }
    $cpuClock = 'core_clk'
    $clockMatches = [regex]::Matches($timing,'(?m)^\s*(\S+)\s+([0-9.]+)\s+\{([^}]+)\}\s+(Generated \([^)]*\)|Declared)\s+(\d+)\s+(\d+)\s+\{([^}]+)\}\s*$')
    $clocks = @($clockMatches | ForEach-Object {[ordered]@{name=$_.Groups[1].Value;period_ns=Number $_.Groups[2].Value;waveform=$_.Groups[3].Value;type=$_.Groups[4].Value;clock_loads=[int]$_.Groups[5].Value;non_clock_loads=[int]$_.Groups[6].Value;source=$_.Groups[7].Value}})
    foreach($expected in (, @($cpuClock,(1e9/145125000)))) {
        $found=@($clocks | Where-Object {$_.name -ceq $expected[0]})
        if($found.Count -ne 1 -or [math]::Abs($found[0].period_ns-$expected[1]) -gt 0.005 -or $found[0].clock_loads -lt 1){throw ('Missing or invalid loaded clock: '+$expected[0])}
    }
    $headers=[regex]::Matches($timing,'(?m)^(Setup|Hold|Recovery|Removal|Minimum Pulse Width) Summary\((Slow|Fast) Corner\):')
    if($headers.Count -ne 10){throw ('Expected ten final multicorner summary tables; found '+$headers.Count)}
    $rows=[System.Collections.Generic.List[object]]::new()
    foreach($header in $headers) {
        $tail=$timing.Substring($header.Index+$header.Length)
        $tableEnd=[regex]::Match($tail,'(?m)^={10,}\s*$')
        if(-not $tableEnd.Success){throw 'Timing summary table is incomplete.'}
        $body=$tail.Substring(0,$tableEnd.Index)
        $divider=[regex]::Match($body,'(?m)^-{10,}\s*$')
        if(-not $divider.Success){throw 'Timing summary divider missing.'}
        $tokens=[System.Collections.Generic.List[string]]::new()
        $count=0
        foreach($line in ($body.Substring($divider.Index+$divider.Length) -split '\r?\n')) {
            if([string]::IsNullOrWhiteSpace($line)){continue}
            foreach($token in ($line.Trim() -split '\s+')){$tokens.Add($token)}
            if($tokens.Count -lt 5){continue}
            $n=$tokens.Count
            if($tokens[$n-4] -match '^-?\d+\.\d+$' -and $tokens[$n-3] -match '^-?\d+\.\d+$' -and $tokens[$n-2] -match '^\d+$' -and $tokens[$n-1] -match '^\d+$') {
                $isPulse=$header.Groups[1].Value -eq 'Minimum Pulse Width'
                if(($isPulse -and $n -ne 5) -or (-not $isPulse -and $n -ne 6)){throw 'Ambiguous timing summary row.'}
                $row=[ordered]@{check=$header.Groups[1].Value;corner=$header.Groups[2].Value;launch_clock=$tokens[0];capture_clock=if($isPulse){$tokens[0]}else{$tokens[1]};worst_slack_ns=Number $tokens[$n-4];total_negative_slack_ns=Number $tokens[$n-3];failing_endpoints=[int]$tokens[$n-2];total_endpoints=[int]$tokens[$n-1]}
                $rows.Add($row);$tokens.Clear();$count++
            }
        }
        if($tokens.Count -ne 0 -or $count -lt 1){throw 'Unparsed or empty timing summary rows.'}
    }
    $paths=[System.Collections.Generic.List[object]]::new()
    foreach($block in ($timing -split '(?m)(?=^Startpoint\s*:)')) {
        $group=[regex]::Match($block,'(?m)^Path Group\s*:\s*(\S+)\s*$')
        $type=[regex]::Match($block,'(?m)^Path Type\s*:\s*(max|min) \((slow|fast) corner\)\s*$')
        if(-not $group.Success -or -not $type.Success -or $type.Groups[1].Value -ne 'max' -or $block -notmatch '\bSetup time'){continue}
        $uncert=[regex]::Match($block,'clock uncertainty\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s*\n\s*Setup time')
        if(-not $uncert.Success){throw 'Detailed setup-path uncertainty missing.'}
        $value=Number $uncert.Groups[1].Value
        if($group.Groups[1].Value -cne $cpuClock){throw 'Unexpected physical clock group.'};$expected=-$ExpectedEffectiveSetupUncertaintyNs
        if([math]::Abs($value-$expected)-gt 0.0001){throw ('Unexpected setup uncertainty on '+$group.Groups[1].Value)}
        $paths.Add([ordered]@{group=$group.Groups[1].Value;corner=$type.Groups[2].Value;uncertainty_ns=$value})
    }
    foreach($corner in @('slow','fast')){if(@($paths|Where-Object{$_.group -ceq $cpuClock -and $_.corner -eq $corner}).Count -lt 1){throw ('No CPU setup-path uncertainty check in '+$corner+' corner')}}
    $physical=($log -split 'Device Utilization Summary :')[-1]
    $resources=[ordered]@{};$lutTotal=0;$ffTotal=0
    foreach($kind in @('CLMA','CLMS')) {
        $match=[regex]::Match($physical,'\| Use of '+$kind+'\s+\|[^\n]+\n\|\s+FF\s+\|\s*(\d+)[^\n]+\n\|\s+LUT\s+\|\s*(\d+)')
        if(-not $match.Success){throw ('Post-route resource block missing: '+$kind)}
        $ff=[int]$match.Groups[1].Value;$lut=[int]$match.Groups[2].Value
        $resources[$kind]=[ordered]@{ff=$ff;lut=$lut};$ffTotal+=$ff;$lutTotal+=$lut
    }
    foreach($kind in @('DRM','GPLL','APM')){ $match=[regex]::Match($physical,'\| Use of '+$kind+'\s+\|\s*([0-9.]+)\s*\|');if(-not $match.Success){throw ('Resource count missing: '+$kind)};$resources[$kind]=Number $match.Groups[1].Value }
    $resources['post_route_luts']=$lutTotal;$resources['post_route_ffs']=$ffTotal
    $violations=@($rows|Where-Object{$_.worst_slack_ns -lt 0 -or $_.failing_endpoints -gt 0 -or [math]::Abs($_.total_negative_slack_ns) -gt 0.0001})
    $summary=[regex]::Match($timing,'Design Summary\s*:\s*([^\r\n]+)').Groups[1].Value.Trim()
    if($rows.Count -ne 10 -or $clocks.Count -ne 1){throw 'Expected ten timing rows and one loaded direct clock.'};$qualified=$violations.Count -eq 0 -and $summary -ceq 'All Constraints Met.'
    $result=[ordered]@{schema='h3-bare-independent-multicorner-audit/v1';release=$Release;build_directory=$build;qualified=$qualified;timing_analysis_mode='multi corner';design_summary=$summary;clock_hz=145125000;configured_setup_uncertainty_ns=0.150;reported_effective_setup_uncertainty_ns=$ExpectedEffectiveSetupUncertaintyNs;uncertainty_scope='Every detailed setup path matches the explicit audit expectation; actual effective uncertainty remains explicit and is compared with the requested minimum separately.';clocks=$clocks;summary_rows=$rows.ToArray();violations=$violations;setup_uncertainty_paths=$paths.ToArray();resources=$resources;report=$reportPath;report_sha256=(Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant();hardware_validated=$false;audited_utc=[datetime]::UtcNow.ToString('o')}
    $output=[System.IO.Path]::Combine($build,'INDEPENDENT_MULTICORNER_AUDIT.json')
    [System.IO.File]::WriteAllText($output,($result|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($true))
    $null=[System.IO.File]::ReadAllText($output)
    Write-Output ('MULTICORNER_AUDIT release='+$Release+' qualified='+$qualified+' tables='+$headers.Count+' clock_pairs='+$rows.Count+' violations='+$violations.Count+' LUT='+$lutTotal+' FF='+$ffTotal+' DRM='+$resources.DRM+' actual_CPU_setup_uncertainty='+$ExpectedEffectiveSetupUncertaintyNs)
    Write-Output ('AUDIT='+$output)
    if(-not $qualified){exit 2}
    exit 0
} catch {
    Write-Error $_
    exit 1
}
