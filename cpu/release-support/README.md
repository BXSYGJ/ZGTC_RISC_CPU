# Shared release build and test tools

These tools support the four RV32IMC folders directly under `cpu/`. The full-ILA RV32IM release has its own loader and rebuild scripts.

## Required software

- PDS 2022.2-SP6.4 with PG2L200H-6FBB676 support, valid license and JTAG/UART drivers for physical builds/programming.
- PowerShell 7+ and Python 3. Firmware and simulation reproduction also use WSL2/Linux with make, G++, GCC and Perl.
- [xPack RISC-V GCC 10.2.0-1.2](https://github.com/BXSYGJ/ZGTC_RISC_CPU/releases/download/qualified-cores-20261012/xpack-riscv-none-embed-gcc-10.2.0-1.2-linux-x64.tar.gz). Verify the archive against `tools/TOOLCHAIN.json`; extract inside Linux. This existing 572,296,735-byte Release asset is not duplicated in Git.
- Original 153/155.25 MHz inferred-memory simulation: extract `tools/verilator-4.038-runtime.tar.gz` inside Linux, preserving permissions and links.
- H3 timed native-memory simulation: build `tools/verilator-5.032-source.tar.gz` inside Linux, then use the resulting Verilator executable and its installed share/verilator include path. Both frozen Pango memory models are included with H3.

All four ready-to-program releases include their firmware; WSL and a compiler are needed only to rebuild or simulate. Use an authenticated browser or GitHub CLI to download the compiler asset if repository access requires authentication.

## Portable commands

Run from any of the four RV32IMC release directories. Select V0 or V1 and new output directories. This example prepares a physical project without invoking PDS.

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $release = (Get-Location).Path
    $scripts = [IO.Path]::GetFullPath([IO.Path]::Combine($release, '..', 'release-support', 'scripts'))
    & ([IO.Path]::Combine($scripts, 'Build-PhysicalProject.ps1')) -ReleaseRoot $release -Role V0 -OutputDirectory ([IO.Path]::Combine('D:/CPUExperiments', 'physical-V0')) -PrepareOnly
    if ($LASTEXITCODE -ne 0) { throw 'Physical project preparation failed.' }
} catch { Write-Error $_ }
```

Remove `-PrepareOnly` and supply `-PdsRoot <installed PDS directory>` to synthesize, route, audit timing and generate a bitstream. The default UART mapping is RemoteLab AC26/AB26. Select `-UartPins LocalBoard` for the alternative B24/C24 mapping; then use the newly built image.

`Build-Firmware.ps1` takes `-ReleaseRoot`, `-Role`, a fresh `-OutputDirectory` and `-GccLinuxPath` (the absolute compiler path inside WSL). `Run-Simulation.ps1` takes those release/output arguments and `-VerilatorLinuxPath`; supply `-VerilatorIncludeLinux` when using an extracted or custom-built tool. `-CompileOnly` compiles without executing the 6,000-iteration benchmark. Each exact compiler/simulator argument list comes from the selected recipe.

`Capture-BoardUART.ps1` takes `-ReleaseRoot`, `-Role`, `-PortName` and a fresh `-OutputDirectory`. Program the matching image first, start capture, then reset the board. `Audit-BoardCapture.ps1` checks an existing `-RawCapture` and writes `-OutputPath`.

`New-ExperimentWorkspace.ps1` creates a separate working copy. Change physical and simulation snapshots together when changing RTL. Every new image requires new timing and board qualification.

## Integrity and evidence

`scripts/Verify-Package.ps1` now defaults to the `cpu/` root and checks `cpu/FILE_MANIFEST.csv`. `Test-ReleaseCollection.ps1` additionally validates source and board bindings, timing, ILA archive hashes and script syntax. Output must be outside the frozen release directories.

`evidence/ARCHIVE_PORTABILITY_VALIDATION.json` and `evidence/PHYSICAL_RESULTS.json` retain earlier two-release upload evidence. `ORIGINAL_UPLOAD_FILE_MANIFEST.csv` is the unchanged historical manifest from the prior nested package; its old paths describe that historical layout. Use `cpu/FILE_MANIFEST.csv` for the current checkout.

The 2026-10-25 upload preserves all original package payloads byte-for-byte. Shared scripts were relocated, and documentation/index files were added. The original local project and manuscript are not changed.
