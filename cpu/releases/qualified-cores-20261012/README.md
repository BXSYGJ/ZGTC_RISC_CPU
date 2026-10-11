# Qualified 155.25 MHz and 153 MHz RV32IMC cores

These are the frozen, full-system, board-qualified releases selected in the project archive. Both execute the performance CoreMark image in 1,782,669,419 measured cycles for 6,000 iterations (3.365739 CoreMark/MHz). Configured-frequency throughput is 522.531 CoreMark at 155.25 MHz and 514.958 at 153 MHz. The 153 MHz release selects the qualified area-optimized implementation at the same best archived throughput. These releases are distinct from the 145.125 MHz H3 paper implementation.

| Release directory | Clock | Performance image | Validation image |
|---|---:|---|---|
| `portable/releases/Original_155250` | 155.25 MHz | V0 | V1 |
| `portable/releases/Original_153000_BestQualified` | 153 MHz | V0 | V1 |

Each release includes author RTL, independent frozen synthesis and simulation snapshots, full peripherals and counters, complete firmware sources and executable images, PLL and pin constraints, PDS routing options, V0/V1 bitstreams, full timing/resource reports, and three accepted cold-board UART captures per image. `recipe.json` fixes all inputs and hashes. Historical absolute paths describe provenance; portable commands use relative snapshots.

## Software and hardware

Use PowerShell 7, Python 3, WSL2 with an x86-64 Linux distribution, GCC/G++, GNU make and Perl. Install Pango Design Suite 2022.2-SP6.4 with PG2L200H-6 FBB676 device support and its normal license configuration. Install board JTAG/UART drivers. The board input clock is 27 MHz; output frequencies are configured PLL frequencies.

The exact Verilator 4.038 inferred-memory runtime is included under `portable/tools`. Extract it inside Linux, retaining permissions and symbolic links, for example under `/opt/core-tools/verilator-4.038`. Its include directory is `/opt/core-tools/verilator-4.038/share/verilator`. These releases use functional RTL simulation, not native timed-memory or post-route simulation.

Download the exact firmware compiler from the repository release:
[xPack RISC-V GCC 10.2.0-1.2](https://github.com/BXSYGJ/ZGTC_RISC_CPU/releases/download/qualified-cores-20261012/xpack-riscv-none-embed-gcc-10.2.0-1.2-linux-x64.tar.gz).
For this private repository, download with an authenticated browser or `gh release download qualified-cores-20261012 --repo BXSYGJ/ZGTC_RISC_CPU --pattern xpack-riscv-none-embed-gcc-10.2.0-1.2-linux-x64.tar.gz --dir ./portable/tools`.
Verify the size and SHA-256 in `portable/tools/TOOLCHAIN.json`, then extract inside Linux under `/opt/core-tools`. The compiler path is `/opt/core-tools/xpack-riscv-none-embed-gcc-10.2.0-1.2/bin/riscv-none-embed-gcc`. Licensed PDS installers and licenses must be installed separately.

## Verify and reproduce

Run the following from this directory. Select either release; repeat each command with V1 for the validation image. Use empty output directories outside the frozen release tree.

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'
try {
    $root = [System.IO.Path]::GetFullPath('.')
    $release = [System.IO.Path]::Combine($root,'portable','releases','Original_155250')
    $scripts = [System.IO.Path]::Combine($root,'portable','scripts')
    $output = [System.IO.Path]::Combine('D:/CPUExperiments','Original155250')
    & ([System.IO.Path]::Combine($scripts,'Verify-Package.ps1')) -PackageRoot $root
    if ($LASTEXITCODE -ne 0) { throw 'Package verification failed' }
    & ([System.IO.Path]::Combine($scripts,'Build-Firmware.ps1')) -ReleaseRoot $release -Role V0 -OutputDirectory ([System.IO.Path]::Combine($output,'firmware-V0')) -GccLinuxPath /opt/core-tools/xpack-riscv-none-embed-gcc-10.2.0-1.2/bin/riscv-none-embed-gcc
    if ($LASTEXITCODE -ne 0) { throw 'Firmware rebuild failed' }
    & ([System.IO.Path]::Combine($scripts,'Run-Simulation.ps1')) -ReleaseRoot $release -Role V0 -OutputDirectory ([System.IO.Path]::Combine($output,'simulation-V0')) -VerilatorLinuxPath /opt/core-tools/verilator-4.038/bin/verilator -VerilatorIncludeLinux /opt/core-tools/verilator-4.038/share/verilator -CompileOnly
    if ($LASTEXITCODE -ne 0) { throw 'Simulation compilation failed' }
    & ([System.IO.Path]::Combine($scripts,'Build-PhysicalProject.ps1')) -ReleaseRoot $release -Role V0 -OutputDirectory ([System.IO.Path]::Combine($output,'physical-V0')) -PdsRoot $env:PDS_ROOT -UartPins RemoteLab -PrepareOnly
    if ($LASTEXITCODE -ne 0) { throw 'Physical preparation failed' }
} catch { Write-Error $_; exit 1 }
```

Remove `-CompileOnly` to execute the full benchmark; the recorded budget is 2.4 billion simulated edges. Remove `-PrepareOnly` to run PDS synthesis, routing, timing analysis and bitstream generation. Each new run requires a fresh output directory. The build script checks all ten timing summaries; clock uncertainty is 0.150 ns, already deducted from slack. Saved reports under each release's `evidence/physical` establish the original routed implementation, not the timing of a fresh placement.

## Real-board measurements

Program `bitstreams/V0.sbit` or `V1.sbit` in PDS using USB JTAG. Saved images use the qualified RemoteLab UART mapping AC26/AB26. The physical build script can instead select `-UartPins LocalBoard` for B24/C24; changed pin mapping requires a new bitstream. Check TX/RX orientation in the corresponding constraint file. UART is 9600 baud, 8N1, no flow control.

Run `Capture-BoardUART.ps1 -ReleaseRoot <release> -Role V0 -PortName <COM port> -OutputDirectory <new directory>`, then reset the board. It waits for READY, sends G and accepts only a complete unchanged START-to-FINISHED frame matching the frozen reference. Repeat three cold captures for V0 and V1. Use `Audit-BoardCapture.ps1` to check saved files offline. CoreMark is computed from the 64-bit cycle count, not rounded UART seconds. All six references per release are included.

## Future experiments and evidence

`New-ExperimentWorkspace.ps1` creates a hashed experimental copy. Update physical and simulation snapshots together when changing RTL. Preserve firmware hashes, CRC checks, raw UART and timing reports. `source/` is author source; the recipe intentionally builds its separate snapshots. The 153 MHz and 155.25 MHz releases have equal measured benchmark cycles but different PLL and routing configurations.

The included portability record documents earlier firmware rebuilds, simulator compilation, timing audits and capture rechecks for all four project releases. This upload contains only the two releases listed above. Upload-time checks verify their bytes, recipes, archived timing reports, complete captures and preparation scripts; they do not assert fresh full simulations, routing or board measurements.
