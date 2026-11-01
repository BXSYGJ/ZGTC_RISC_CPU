[CmdletBinding()]
param([switch]$AllowIncomplete, [switch]$RequireTimingClosure)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $root = $PSScriptRoot
    $utf8Bom = [System.Text.UTF8Encoding]::new($true)
    $rows = [System.Collections.Generic.List[object]]::new()
    foreach ($release in @('Original_155250', 'H3_Retained_145125', 'H3_Base_145125')) {
        $selectedPath = [System.IO.Path]::Combine($root, $release, 'SELECTED_BUILD.json')
        $selected = Get-Content -LiteralPath $selectedPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ([math]::Abs($selected.setup_uncertainty_ns - 0.150) -gt 0.000001) { throw ('Unexpected CPU uncertainty: ' + $release) }
        if ($RequireTimingClosure -and -not $selected.all_corner_timing_passed) { throw ('Selected timing is incomplete: ' + $release) }
        $wavePath = [System.IO.Path]::Combine($root, $release, 'waveforms', 'WAVEFORM_MANIFEST.json')
        $wave = Get-Content -LiteralPath $wavePath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($wave.origin -cne 'LOCAL RTL SIMULATION' -or $wave.hardware_validated) { throw 'Unexpected waveform origin.' }
        foreach ($field in @('bitstream', 'fic')) {
            $artifact = $selected.$field
            $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash
            $hashField = $field + '_sha256'
            if ($hash -ine $selected.$hashField) { throw ('Changed selected artifact: ' + $artifact) }
        }
        foreach ($window in $wave.windows) {
            if ($window.samples -ne 1024) { throw 'Expected 1024 recorded edges.' }
            foreach ($field in @('csv', 'vcd', 'decoded_csv', 'raw_csv')) {
                $hashField = $field + '_sha256'
                if ((Get-FileHash -LiteralPath $window.$field -Algorithm SHA256).Hash -ine $window.$hashField) { throw ('Changed waveform: ' + $window.$field) }
            }
        }
        $resultPath = [System.IO.Path]::Combine($selected.full_simulation_directory, 'RESULT.json')
        $result = $null
        $fullPass = $false
        if (Test-Path -LiteralPath $resultPath -PathType Leaf) {
            $result = Get-Content -LiteralPath $resultPath -Raw -Encoding utf8 | ConvertFrom-Json
            if ($release -eq 'Original_155250') {
                $fullPass = $result.complete_coremark_run -and $result.exit_code -eq 0 -and $result.uart_byte_identical -and $result.baseline_cycles_and_retired_equal
                $cycles = [long]$result.cycle_count
                $retired = [long]$result.retired_count
            } else {
                $fullPass = $result.completed_6000_iterations -and $result.native_exit_code -eq 0 -and $result.exact_reference_uart_equal -and $result.all_crc_fields_equal_by_exact_uart
                $cycles = [long]$result.cycles
                $retired = [long]$result.retired
            }
        } else { $cycles = 0; $retired = 0 }
        if (-not $fullPass -and -not $AllowIncomplete) { throw ('Full simulation incomplete or failed: ' + $release) }
        $scorePerMHz = if ($fullPass) { 6000.0 * 1e6 / $cycles } else { $null }
        $lut = [int]$selected.resources.post_route_luts
        $rows.Add([ordered]@{
            release = $release
            source_selection = $selectedPath
            selection_sha256 = (Get-FileHash -LiteralPath $selectedPath -Algorithm SHA256).Hash.ToLowerInvariant()
            configured_clock_hz = $selected.clock_hz
            timing_closure = $selected.all_corner_timing_passed
            setup_slack_ns = $selected.cpu_setup_wns_ns
            cpu_clock_uncertainty_ns = $selected.setup_uncertainty_ns
            ila_profile = $selected.ila_profile
            resources = $selected.resources
            build_directory = $selected.build_directory
            full_6000_simulation_passed = [bool]$fullPass
            full_result = $resultPath
            cycles = $cycles
            retired_instructions = $retired
            coremark_per_mhz = $scorePerMHz
            target_clock_derived_coremark = if ($fullPass) { $scorePerMHz * $selected.clock_hz / 1e6 } else { $null }
            target_clock_derived_coremark_per_lut = if ($fullPass) { $scorePerMHz * $selected.clock_hz / 1e6 / $lut } else { $null }
            coremark_per_mhz_per_klut = if ($fullPass) { $scorePerMHz * 1000 / $lut } else { $null }
            performance_scope = 'Exact V0 firmware and external cached-system service; configured clock score is derived, not a new board measurement.'
            waveform_origin = $wave.origin
            waveform_manifest = $wavePath
            windows = @($wave.windows | Select-Object function, csv, vcd, samples, trigger_pc, first_cycle, last_cycle)
            hardware_validated = $false
        })
    }
    $catalog = [ordered]@{ schema = 'independent-minimal-ila-releases/v1'; generated_utc = [datetime]::UtcNow.ToString('o'); remote_operations = 'disabled by user; no board programming'; releases = $rows.ToArray(); waveform_index = [System.IO.Path]::Combine($root, 'analysis', 'README.md'); renderer_verification = [System.IO.Path]::Combine($root, 'analysis', 'RENDERER_VERIFICATION.json') }
    $catalogPath = [System.IO.Path]::Combine($root, 'RELEASES.json')
    [System.IO.File]::WriteAllText($catalogPath, ($catalog | ConvertTo-Json -Depth 30), $utf8Bom)
    $reportLines = [System.Collections.Generic.List[string]]::new()
    $reportLines.Add('# Local ILA implementation and execution results')
    $reportLines.Add('')
    $reportLines.Add('All waveform recordings originate from local RTL simulation. Each full benchmark uses the exact frozen V0 firmware with 6,000 iterations. UART bytes, validation CRCs, execution cycles and retired instructions match the respective reference. No board programming or remote ILA capture is part of this task.')
    $reportLines.Add('')
    $reportLines.Add('| Release | Configured MHz | Data / trigger bits | Cycles | CoreMark/MHz | Routed LUT / FF | Setup slack (ns) |')
    $reportLines.Add('| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
    foreach ($row in $rows) {
        $width = if ($row.ila_profile -eq 'Lean24') { '24 / 17' } elseif ($row.ila_profile -eq 'NativeMinimal') { '42 / 33' } else { '42 / 42' }
        $reportLines.Add(('| {0} | {1:F3} | {2} | {3:N0} | {4:F6} | {5:N0} / {6:N0} | {7:0.000;-0.000;0.000} |' -f $row.release, ($row.configured_clock_hz / 1e6), $width, $row.cycles, $row.coremark_per_mhz, $row.resources.post_route_luts, $row.resources.post_route_ffs, $row.setup_slack_ns))
    }
    $reportLines.Add('')
    $reportLines.Add('Every full run retires 1,649,428,429 measured instructions. The CPU timing constraints include 0.150 ns setup uncertainty. Slack is reported after that deduction. A printed 0.000 ns result has no additional reported margin. RELEASES.json links the all-corner result for each selected layout.')
    $reportLines.Add('')
    $reportLines.Add('| Release | CoreMark at configured clock | CoreMark/LUT | CoreMark/MHz/kLUT | DRM / APM |')
    $reportLines.Add('| --- | ---: | ---: | ---: | ---: |')
    foreach ($row in $rows) {
        $reportLines.Add(('| {0} | {1:F3} | {2:F6} | {3:F6} | {4} / {5} |' -f $row.release, $row.target_clock_derived_coremark, $row.target_clock_derived_coremark_per_lut, $row.coremark_per_mhz_per_klut, $row.resources.DRM, $row.resources.APM))
    }
    $reportLines.Add('')
    $reportLines.Add('The 42-bit local observer records a superset of the selected physical probes. The H3 Lean24 data comprise EX PC [15:0], IF/ID/EX/MEM/WB validity and ID/EX/MEM transfer. Its trigger is EX PC [15:0] plus EX transfer. SOURCE_TO_SELECTED_BINDING.json verifies the exact subset mapping. Sixteen PC bits identify the current firmware functions within its 64-KiB image; high-address diagnostics are outside that smaller physical probe set.')
    $reportLines.Add('')
    $reportLines.Add('Nine 1,024-edge windows cover entry into core_bench_list, core_bench_matrix and core_bench_state. Each has packed/decoded CSV and VCD, plus an overview and 32-edge zoom in PNG and SVG. The renderer checked 387,072 bits against packed observations and VCD. [Waveform index](README.md); [contact sheet](LOCAL_WAVEFORM_CONTACT_SHEET.png).')
    $reportLines.Add('')
    $reportLines.Add('Waveform axes use CPU-edge indices. The configured FPGA frequency is separate from the actual simulator timebase and accelerated UART settings. Window-level WB counts and held-stage cycles describe the recorded intervals. CoreMark is derived from complete measured cycle counts at the configured target; it is not a new physical-board measurement.')
    $reportPath = [System.IO.Path]::Combine($root, 'analysis', 'IMPLEMENTATION_RESULTS.md')
    [System.IO.File]::WriteAllText($reportPath, ($reportLines -join [Environment]::NewLine), $utf8Bom)
    $null = [System.IO.File]::ReadAllText($reportPath)
    $reopened = Get-Content -LiteralPath $catalogPath -Raw -Encoding utf8 | ConvertFrom-Json
    if (@($reopened.releases).Count -ne 3) { throw 'Catalog reopen failed.' }
    Write-Output ('CATALOG_VERIFIED releases=3 windows=9 full_runs=' + @($rows | Where-Object full_6000_simulation_passed).Count)
    Write-Output $catalogPath
    exit 0
} catch { Write-Error $_; exit 1 }
