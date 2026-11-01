# ZGTC_RISC_CPU

RV32IMC soft-core releases for the Pango PG2L200H FPGA, with sources, firmware, physical implementation reports and validation evidence.

## New: minimal ILA and bare-core results — 2026-11-01

The [new release collection](cpu/validated-extensions-20261101/README.md) adds independent minimal-ILA versions of **Original 155.25 MHz**, **H3 Retained 145.125 MHz**, and **H3 Base 145.125 MHz**, plus their separately routed bare-core extractions.

| Release | MHz | CoreMark/MHz | Complete ILA system LUT / FF | Extracted core LUT / FF |
|---|---:|---:|---:|---:|
| Original | 155.250 | 3.365739 | 6,609 / 3,573 | 4,028–4,031 / 1,543 |
| H3 Retained | 145.125 | 3.442075 | 6,456 / 3,024 | 4,143–4,147 / 1,554 |
| H3 Base | 145.125 | 3.441903 | 6,421 / 3,024 | 4,095–4,107 / 1,528 |

All six selected implementations meet their checked internal timing constraints. Additions include RTL, frozen firmware, selected bitstreams/reports, SHA-256 inventories, rebuild preparation tools and [nine waveform windows](cpu/validated-extensions-20261101/workspace/ILA_Core_Releases_20261101/analysis/README.md) with PNG/SVG/CSV/VCD files.

New waveforms are **local RTL simulations**, not board ILA captures. Full 6,000-iteration source-system simulations preserve reference firmware, UART bytes, cycles and retired counts. Bare-core performance is joined to those source runs through byte-identical RTL and extraction checks; bare-core area excludes external caches, memories, peripherals and the scan fixture. See the release README for exact scope, timing uncertainty, resource efficiency and reproduction commands.

## Board-qualified CPU releases

The [CPU index](cpu/README.md) retains five separately packaged board-qualified releases: H3 Base 145.125 MHz, H3 Retained 145.125 MHz, Original 153 MHz, Original 155.25 MHz, and the selected full-ILA RV32IM 153 MHz build. Each includes sources, firmware, board references and implementation records. The best archived 153 MHz version remains available.

[Shared build and test tools](cpu/release-support/README.md) support the existing collection. The older [full-fetch 153 MHz experiment](cpu/experiments/full_fetch_commit_factored/README.md) remains historical evidence; its 9,502-LUT system is distinct from the selected releases.

## PCB AOI vision and training dataset

The [PCB AOI archive](pcb-aoi/README.md) contains the YOLOv8n detector, CNN implementation references, trained PyTorch/ONNX weights, and the recovered 1,164-image training / 66-image validation dataset, with 195 field-image archive copies and verification reports.
