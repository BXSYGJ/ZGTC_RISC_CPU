# GitHub release location

This folder contains the performance-selected full-ILA package recovered from the project archive. It achieves 511.722 CoreMark in V0 at 153 MHz and retains 42 data channels, 33 trigger channels and a 1,024-sample depth. It is RV32IM; the other four folders are RV32IMC.

Run the commands below with `$ilaPackage` set to this cloned folder. From the repository root, use `[IO.Path]::Combine((Get-Location).Path, 'cpu', 'Accepted_RV32IM_153000_FullILA')`. The existing `Prepare-Rebuild.ps1` and `Test-CoreMarkBoard.ps1` are local to this folder. Its UART loader uses **115200 baud**, unlike the 9600-baud embedded images in the other releases.

The archived package, all 1,703 recovered payload files, bitstream, original ILA mappings and final board/RTL review are preserved. `PERFORMANCE.json` records both configurations. The complete five-release hash manifest is `../FILE_MANIFEST.csv`.

---

# Board-qualified 153 MHz full-ILA release

This package restores the performance-selected, historically qualified ILA release from `AAAFPGA_Relocated_20261012(1).zip`. It is an RV32IM accepted-storage implementation, not the later RV32IMC release. Its 7,312 LUTs are an explicit exception to the collection's original sub-7,000-LUT scope. The source archive and original evidence remain unchanged.

| Reference measurement | Value |
|---|---:|
| Configured CPU frequency | 153 MHz |
| Routed LUT / FF | 7,312 / 4,023 |
| DRM / APM | 22.5 / 4 |
| Setup slack, with 0.150 ns uncertainty | +0.053 ns |
| Minimum reported multicorner hold slack | +0.102 ns |
| CoreMark V0, 6,000 iterations | 511.722088 |
| CoreMark/MHz | 3.344589 |
| CoreMark/LUT | 0.0699839 |
| CoreMark/MHz/kLUT | 0.457411 |
| V0 cycles / retired instructions | 1,793,942,498 / 1,649,428,429 |
| ILA data / trigger channels / depth | 42 / 33 / 1,024 samples |

Frequency is the configured PLL rate, not an independent frequency-counter measurement. The final joint review records six cold-programmed observations, three per firmware configuration, matching the full-length RTL runs. V1 is a separate validation configuration: 511.846268 CoreMark, 1,793,507,264 cycles and 1,649,775,527 retired instructions. Keep V0 and V1 results separate.

## Files to use

All paths below are relative to this directory. `project/cpu_paper/results/` retains the original evidence layout.

- `bitstreams/FullILA_153MHz.sbit`: convenience copy of the qualified bitstream. SHA-256: `c7cc550011e051a9ac91131a67c696d4244e5b84d6bd15b020c8fad566814feb`.
- `project/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/`: frozen RTL inputs, constraints, PLL, loader image, tool snapshots, synthesis and implementation projects, FIC debug mapping, netlist, ADF and timing/resource reports.
- `project/cpu_paper/results/coremark-ablation-20260924T152600Z-68132642/firmware/V0/` and `V1/`: executable firmware binaries, ELF, HEX and build records. These applications load into RAM; both use the same loader bitstream.
- `project/cpu_paper/results/selected-coremark-board-20260924T165919Z-a05b26e2/`: original serial captures and board-run records.
- `project/cpu_paper/results/selected-coremark-board-review-20260924T210607Z-162ca189/review.json`: final board/full-RTL qualification. Earlier intermediate manifests can still say validation was pending; this final review supersedes that status.
- `project/cpu_paper/results/accepted-area-physical-review-20260924T154119Z-a46dc4c2/review.json`: physical resource/timing review.
- `project/cpu_paper/results/coremark-loader-rtl-20260924T152726Z-315bd383/`: archived full-length RTL evidence.
- `EXTRACTED_FILE_MANIFEST.csv`: original archive mappings and hashes for all 1,703 recovered files.

## Run on a compatible board

Use a Pango Logos2 PG2L200H-6FBB676 board with the archived board and UART pin constraints. Check pin compatibility before programming another board model. Install PDS 2022.2-SP6.4, its JTAG driver and a valid license, and PowerShell 7+. No remote-lab credentials are included or needed for the local UART script.

1. Connect JTAG and UART USB, power the board, and program `bitstreams/FullILA_153MHz.sbit` using the PDS programmer. Do a fresh program/reset for each observation.
2. Identify the board's UART COM port. Run the following in PowerShell 7, replacing the package, results and COM-port values. The script does not program JTAG.

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ilaPackage = 'D:/AAAFPGA/Current_Paper_and_Sub7000_Core_Releases_20261012/cores/Accepted_RV32IM_153000_FullILA'
$captureDirectory = [System.IO.Path]::Combine('D:/ILA_Experiments', 'V0_run1')
& ([System.IO.Path]::Combine($ilaPackage, 'Test-CoreMarkBoard.ps1')) -PortName COM5 -Configuration V0 -OutputDirectory $captureDirectory
```

The UART is 115200 baud, 8N1, without flow control. The script verifies the firmware hash, queries `ZBOOT READY R`, sends `R` and the little-endian binary length, then transfers 256-byte chunks with `K` acknowledgements. It checks the RAM CRC and byte count, waits for application READY and sends `G`. The application starts at 0x1000; the loader occupies 0x0000–0x0fff. Capture includes the complete benchmark completion marker. Raw bytes are retained even on a failed transfer.

The new uploader checks reference counts but does not replace the historical complete-output/CRC audit. Compare each new complete UART capture against the corresponding archived observation before calling it qualified. V0's RAM CRC is `bba62a9a`, final CoreMark CRC `a14c`; V1's are `2fe4a47a` and `18e1`. The new uploader has been syntax-checked, not tested against a connected board during recovery.

## Relocate and rebuild the physical implementation

Use `Prepare-Rebuild.ps1` to make a separate working copy and replace original absolute paths in its textual project files. It leaves all frozen evidence unchanged. First prepare without launching PDS:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ilaPackage = 'D:/AAAFPGA/Current_Paper_and_Sub7000_Core_Releases_20261012/cores/Accepted_RV32IM_153000_FullILA'
$workDirectory = [System.IO.Path]::Combine('D:/ILA_Experiments', 'rebuild_seed3')
& ([System.IO.Path]::Combine($ilaPackage, 'Prepare-Rebuild.ps1')) -WorkDirectory $workDirectory -PdsHome 'D:/PDS_2022.2-SP6.4'
```

Add `-RunPds` with a new working directory to run the archived implementation recipe in the background. PDS executes `implementation/build.tcl` with seed 3, LUT combining strategy 3 and decongestion 0. This rebuild starts from the frozen synthesized netlist and ADF and retains the mapped ILA channels. The corresponding project is `implementation/cpu_ila.pds`; the FIC is `implementation/cpu-remapped.fic`. Open the relocated FIC with the PDS debug tool when inspecting the qualified image.

Fresh RTL synthesis is a separate operation: the original synthesis recipe and sources are included, but new synthesis can rename signals. Recreate and audit the ILA mapping before routing newly synthesized logic, using the frozen `inputs/tools/runner.py`, alias and ILA-audit snapshots as the workflow reference. Do not reuse the old FIC blindly. The recovery-stage rebuild preparation has been tested; PDS routing and new hardware qualification have not been rerun. Every rebuilt image needs its own timing report and board checks.

## Recovery provenance

Downloaded archive: `D:/Quark_cache/AAAFPGA_Relocated_20261012(1).zip`.
Archive SHA-256: `3aed6da97e622917246be91341870a54f53fdcdafadba6ec491fd022fbe6237d`.
All extracted payloads were verified against the original per-file SHA-256 records. No new compressed archive or manuscript revision was produced for this addition.
