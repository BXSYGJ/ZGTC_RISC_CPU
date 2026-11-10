# CODEBUDDY.md

> **已归档（2026-11-10）**：本文件描述的是 200H 时代结构，AGENTS.md 已明确其过时。
> 当前入口见 `AGENTS.md`；快照总览见 `docs/SNAPSHOT_INDEX.md`。

This file provides guidance to CodeBuddy Code when working with code in this repository.

## What this repository is

A RISC-V CPU/SoC for the 全国大学生 FPGA 创新设计竞赛 紫光同创 (Pango) track, topic 1. Target device
**Pango PG2L200H-6FBB676** on the **MES2L676-200HP** board. The accepted result is an RV32IM SoC at a
configured **153 MHz / 511.318 CoreMark**.

Two things surprise almost everyone on first contact — read these before touching anything:

1. **The top-level `cpu/rtl` is not the accepted implementation.** It is the mainline integration RTL used
   for simulation, lint and the general regression suite. The provisionally accepted 153 MHz build lives in
   **`cpu/experiments/full_fetch_commit_factored/`**, which carries its own `rtl/`, `sim/`, `sw/`,
   `scripts/`, `constraints/`, `fpga/` and `configuration.json`. Older README/文档的 “当前/正在运行”
   statements are historical; do not treat them as live jobs.
2. **`cpu/experiments/` holds ~148 frozen microarchitecture experiments**, each an isolated RTL variant with
   its own evidence. They are referenced by parent/child hashes, not by shared code. Do not "clean up" or
   refactor across them.

## Environment

Everything is Windows-first; simulation runs inside WSL.

| Piece | Requirement |
| --- | --- |
| Shell | **PowerShell 7 (`pwsh`)**, not Bash / Git Bash, for all script entry points |
| WSL | distribution **`Ubuntu-22.04`** — this name is hardcoded in every script |
| Simulators in WSL | Icarus Verilog (`iverilog` / `vvp`), Verilator (`--lint-only --Wall`), `python3` |
| Implementation (Windows) | Pango **PDS 2022.2-SP6.4**; `PDS_ROOT` env var, default `D:/PDS_2022.2-SP6.4` |
| PDS license | user env var `PANGO_LICENSE_FILE` must be set or every PDS script throws |
| RV32 toolchain A (canonical) | self-built `riscv32-unknown-elf-gcc` 10.2.0 inside WSL; manifest at `cpu/build/riscv32-toolchain.json`, resolved by `cpu/scripts/riscv_toolchain.ps1` |
| RV32 toolchain B (no-WSL path) | Windows xPack `riscv-none-elf-*` 15.2.0; lookup order `$env:RV32_TOOLCHAIN` → `H:/ST/RV32I` → `D:/ST/RV32I`. See `docs/NO_WSL_TOOLCHAIN.md` |

Build the canonical toolchain once before the first full validation:

```powershell
wsl.exe --distribution Ubuntu-22.04 --user root --exec /usr/bin/apt-get install -y --no-install-recommends build-essential bison flex texinfo libgmp-dev libmpfr-dev libmpc-dev zlib1g-dev
pwsh -NoProfile -File cpu/scripts/build_riscv32_toolchain.ps1 -Jobs 8
```

Scripts never fall back to an RV64 compiler: they check the target/version and fail loudly.

## Common commands

Run all of these **from the repository root**.

### Full regression (the one gate that matters)

```powershell
pwsh -NoProfile -File cpu/scripts/validate.ps1
```

Chains unit tests → CPU differential → M-extension → cached/uncached → SoC IRQ → checker-mutation
tests → Verilator lint across many parameter combinations. It is long; run it, don't subset it.

Individual phases, if you only need one:

```powershell
pwsh -NoProfile -File cpu/scripts/run_tests.ps1              # unit tests (iverilog, ~40 testbenches)
pwsh -NoProfile -File cpu/scripts/run_core_tests.ps1         # bare CPU vs Python reference model
pwsh -NoProfile -File cpu/scripts/run_core_tests.ps1 -BtbIndexBits 6 -EarlyDRequest
pwsh -NoProfile -File cpu/scripts/run_muldiv_core_tests.ps1  # RV32M + precise interrupts
pwsh -NoProfile -File cpu/scripts/run_cached_tests.ps1 -FastICacheHit -LoadUseBubble
pwsh -NoProfile -File cpu/scripts/run_soc_tests.ps1 -ExternalUart -CacheEnabled 0
pwsh -NoProfile -File cpu/scripts/run_gpio_tests.ps1
pwsh -NoProfile -File cpu/scripts/run_asymmetric_tests.ps1
pwsh -NoProfile -File cpu/scripts/run_scope_tests.ps1
```

### Running a single test

Python checkers/tests are plain scripts — run them directly on Windows or through WSL:

```powershell
python cpu/scripts/test_btb_address_bounds.py
python cpu/scripts/test_cache_lru_storage.py
```

The reference model re-check of one CPU trace:

```powershell
python cpu/scripts/check_trace.py cpu/build/core_selftest.bin cpu/build/core_p1_12345678.trace --memory cpu/build/core_p1_12345678.memory
```

One unit testbench end-to-end:

```powershell
wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s btb_tb -o /mnt/d/<repo>/cpu/build/btb.vvp /mnt/d/<repo>/cpu/rtl/rv32_btb.sv /mnt/d/<repo>/cpu/sim/btb_tb.sv
wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp /mnt/d/<repo>/cpu/build/btb.vvp
```

Lint (three separate top modules, each with its own source list — see `validate.ps1` lines 136-172):

```powershell
wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_core <core sources>
wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_memory_system <memory sources>
wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top <all rtl/*.sv>
```

### External ISA tests

```powershell
pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1                                   # 41 RV32UI programs, 164 runs
pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1 -Suite rv32um -EnableM 1
```

Downloads a **hash-pinned** `riscv-tests` tarball; a hash mismatch is a hard failure.

### CoreMark simulation

```powershell
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -ClockHz 90000000
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -ClockHz 90000000 -ValidationRun
```

`-ClockHz` and `-Iterations` are `ValidateSet`-restricted. The benchmark sources are cloned at a pinned
revision and the script refuses to proceed if the checkout is dirty.

### Windows PDS implementation (synthesis → bitstream)

```powershell
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile Board
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile RemoteLab -FlashBoot
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile RemoteLab -ClockHz 153000000 -EnableM 1 -ICacheSetBits 9 -BtbIndexBits 8 -PlacementSeed 1
```

`Board` and `RemoteLab` are alternative UART pinouts (Board = B24/C24; RemoteLab = RX AC26 / TX AB26),
**not** sequential steps. `-FlashBoot` puts only the bootloader in BRAM. A non-default `-ClockHz` requires a
matching `firmware.build.json` manifest. Results land in `cpu/build/pds/<timestamp>-<rand>/`, with
`source-snapshot.json` recording the SHA-256 of every input.

### Hardware (remote experiment box)

```powershell
python -m uvicorn fpga_lab_server.app:create_app --factory --host 127.0.0.1 --port 8600   # from tool/fpga_lab
python tool/fpga_lab/coremark_verify.py        # reserve box → burn 153 MHz bitstream → load CoreMark → score
python tool/fpga_lab/ram_load.py cpu/build/app_big.bin
```

### Handoff integrity check (works on a fresh clone)

```powershell
python cpu/scripts/verify_153mhz_handoff.py
```

### Board baseline (`pds_minimal_blink_200h/`, no CPU)

```powershell
pwsh -File .\scripts\run_wsl_sim.ps1
pwsh -File .\scripts\run_pds_full.ps1
```

## Architecture

### RTL (`cpu/rtl/`, SystemVerilog, one module per file)

Pipeline: `取指请求 → IF 缓冲 → ID 译码/寄存器读取 → EX 执行/前递 → MEM 访存与控制提交 → WB 写回`.

| File | Role |
| --- | --- |
| `rv32_core.sv` | 5-stage in-order pipeline, forwarding, hazard/flush logic, `trace_*` observer outputs |
| `rv32_decode.sv` | combinational decoder → control flags, immediate, `illegal` |
| `rv32_alu.sv` | carry-select adder, shifts, SLT/SLTU, logic |
| `rv32_muldiv.sv` | RV32M unit; parallel half-word products, restoring divider |
| `rv32_btb.sv` | direct-mapped BTB + 2-bit saturating counters, hashed/folded index |
| `rv32_machine.sv` | M-mode CSRs, Zicsr, precise traps, MRET, `mcycle`/`minstret` |
| `rv32_cache.sv` | set-associative I/D cache core; write-back/write-allocate, byte write enables |
| `rv32_uncached.sv` | non-cacheable path with the same burst interface |
| `rv32_memory_system.sv` | two caches + burst round-robin arbiter + on-chip RAM + uncached MMIO port |
| `rv32_burst_arbiter.sv` | burst-locked round-robin arbiter |
| `rv32_burst_ram.sv` | synthesizable on-chip RAM with `INIT_FILE` |
| `rv32_soc.sv` | CPU + memory system + peripherals + SPI flash controller |
| `rv32_board_top.sv` | pin-level top (clock, reset, key, UART, SPI, LEDs) |
| `rv32_peripherals.sv` | MMIO register block: UART, GPIO, 64-bit timer, software IRQ, status, SPI |
| `rv32_uart.sv`, `rv32_fifo.sv`, `rv32_spi_flash.sv` | peripherals |

### Compile-time configuration

Nearly every optimization is a module parameter, all defaulting to off, so one RTL tree serves every
experiment. On `rv32_core`: `RESET_VECTOR`, `ENABLE_PREDICTOR`, `ENABLE_M`, `FETCH_OVERLAP`,
`EARLY_D_REQUEST`, `BTB_INDEX_BITS`, `LOAD_USE_BUBBLE`. On `rv32_soc` / `rv32_board_top` additionally:
`FAST_ICACHE_HIT`, `FAST_DCACHE_READ`, `FAST_DCACHE_WRITE`, `DATA_OVERLAP`, `ICACHE_SET_BITS`,
`CACHE_SET_BITS`, `ENABLE_CACHE`, `CLOCK_HZ`, `INIT_FILE`. `rv32_cache` mirrors these as `READ_ONLY`,
`FAST_READ_HIT`, `FAST_WRITE_HIT`, `READ_OVERLAP`.

The qualified 153 MHz configuration (`cpu/experiments/full_fetch_commit_factored/configuration.json`) turns
**all** of them on: `EnableM=1`, `ICacheSetBits=9` (16 KiB), `CacheSetBits=6`, `BtbIndexBits=8`,
`LoadUseBubble=1`, all five fast/overlap switches, `ClockHz=153000000`.

### Memory map

64 KiB on-chip BRAM (no DDR). Bootloader occupies the first 4 KiB at `0x0000`; applications link to
`0x1000` (`cpu/sw/link_soc.ld`) and get 60 KiB. MMIO starts at `0x10000000`:
`STATUS 0x10000000`, `UART_* 0x10000100`, `GPIO_* 0x10000200`, `TIME/COMPARE/SOFTWARE_IRQ 0x10000300`,
`SPI_* 0x10000500`.

### Experiment layout (`cpu/experiments/<name>/`)

Each experiment is a self-contained, provenance-tracked variant:

- `configuration.json` — the parameter set and clock for that variant
- `source-inputs.json` — parent experiment path plus SHA-256 of all ~20 physical source files
- `change-receipt.json` — the parent→candidate RTL delta as exact string substitutions
- `prepare_*.py` — re-derives candidate RTL from the parent and verifies both hashes; **do not run it on
  already-accepted directories**
- `audit_*.py` — produces/verifies evidence receipts (pairing, resource binding, ILA, hardware)
- `test_*.py` — negative controls / mutation tests for that variant
- `run_physical.ps1`, `run_long.ps1`, `run_full_ila.ps1` — guarded runners; each checks free memory, refuses
  to run when another PDS/WSL instance is active, and refuses to overwrite an existing log

Long CoreMark simulations use a **6,000,000,000-cycle** overall watchdog (startup + timed interval + pauses +
result output). An earlier 2.1e9 limit produced a rejected run that is deliberately preserved.

### Verification methodology (follow it, it is the project's core convention)

- Every CPU run is diffed against an independent Python reference model (`check_trace.py`) that checks
  retired instructions, register values, precise traps and final memory.
- Every checker has **mutation/negative-control tests** proving it rejects wrong PC / instruction / writeback
  / trap records. A new checker without a rejecting test is not accepted.
- Upstream archives (`riscv-tests`, CoreMark) are **revision- and hash-pinned**.
- Failed and rejected runs, bitstreams and captures are **kept, never overwritten**.

## Project conventions

- Daily development and verification commits go to branch **`DYH`** (the working tree is currently on `XSY`
  after the XSY×DYH merge — check `git branch` before committing).
- **Never push to GitHub unless explicitly asked.** Several docs repeat: do not auto-push subsequent updates.
- Not committed: PDS databases, intermediate implementation directories, logs, simulation output, bitstreams,
  local licenses, `account.txt` (credentials). RTL, testbenches, constraints, scripts and docs *are* committed.
- `.gitattributes` sets `-text` on `cpu/experiments/**` and `cpu/docs/evidence/**` — these are
  **byte-preserving** because hashed evidence depends on exact bytes. Do not reformat or re-normalize them.
- Serialize PDS: never run two `pds_shell` instances at once; the runners enforce it.
- Report CoreMark as `6000 × clock / timed_cycles` from the 64-bit ZGTC counters. **Never report 545** —
  that is the legacy UART integer `Iterations/Sec` line.
- Report **three metrics separately** (CoreMark, CoreMark/MHz, CoreMark/LUT). Never claim all three improved
  unless each actually did; the docs consistently refuse Pareto claims over intermediate candidates.
- 153 MHz is a **configured** clock, not independently measured. SCBV is unset; electrical/CDC review and
  long-duration stability are open caveats. Do not upgrade "board bring-up succeeded" into certification.
- Do not put credentials (platform account, auth headers, tokens) into Git, docs or logs.

## Where to find authoritative detail

- `cpu/docs/AI_HANDOFF_153MHZ.md` — binding continuation note; `cpu/docs/PROJECT_HANDOVER_153MHZ.md` — human
  narrative; `cpu/docs/ACCEPTANCE.md` — requirement ledger with the current stopping criterion.
- `cpu/docs/TOOLCHAIN.md` — RV32 toolchain construction; `docs/NO_WSL_TOOLCHAIN.md` — Windows-only path.
- `cpu/docs/FLASH_BOOT.md` — boot flow, bootloader console (`W`/`R`/`B`/`E`/`?` commands). Note `W` is
  physically unavailable: the U9 clock pin H13 is a dedicated config pin, so delivery uses `R` (load to RAM).
- `cpu/docs/BUS.md` — memory interface; `cpu/docs/PERIPHERALS.md` — MMIO; `cpu/docs/CLOCKING.md` — PLL.
- `DEV_SNAPSHOT.md` — repo-level handover, environment table, known pitfalls (bridge service dies after
  ~10 min idle; large payloads need 256-byte chunking with `K` acknowledgements).
- `cpu/docs/` has ~175 experiment write-ups, one per optimization; each is the evidence of record for that
  measurement.
