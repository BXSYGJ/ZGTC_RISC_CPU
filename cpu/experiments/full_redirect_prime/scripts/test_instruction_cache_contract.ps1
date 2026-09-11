[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $checks = 0
    foreach ($name in @('run_cached_tests.ps1','run_coremark_test.ps1','run_isa_tests.ps1','run_soc_tests.ps1','run_pds.ps1')) {
        $path = [IO.Path]::Combine($PSScriptRoot, $name)
        $tokens = $null; $parseErrors = $null
        $tree = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$parseErrors)
        if ($parseErrors.Count) { throw ('PowerShell parse failure: ' + $name) }
        $probe = [scriptblock]::Create($tree.ParamBlock.Extent.Text + [Environment]::NewLine + '$ICacheSetBits')
        foreach ($bits in @(0,1,8,9,10)) {
            $result = & $probe -ICacheSetBits $bits
            if ($result -ne $bits) { throw ('Instruction width changed during binding: ' + $name) }
            $checks++
        }
        foreach ($bits in @(-1,11,16,1024)) {
            $rejected = $false
            try { $null = & $probe -ICacheSetBits $bits } catch [Management.Automation.ParameterBindingException] { $rejected = $true }
            if (-not $rejected) { throw ('Invalid instruction width accepted: ' + $name) }
            $checks++
        }
        foreach ($field in @('CacheSetBits','BtbIndexBits')) {
            if ($tree.ParamBlock.Parameters.Name.VariablePath.UserPath -notcontains $field) { continue }
            foreach ($bits in @(9,10)) {
                $arguments = @{}; $arguments[$field] = $bits
                $rejected = $false
                try { $null = & $probe @arguments } catch [Management.Automation.ParameterBindingException] { $rejected = $true }
                if (-not $rejected) { throw ('Unrelated width limit widened: ' + $name + ':' + $field) }
                $checks++
            }
        }
    }
    Write-Output "PASS instruction cache PowerShell contracts checks=$checks"
} catch {
    Write-Error $_
    exit 1
}
