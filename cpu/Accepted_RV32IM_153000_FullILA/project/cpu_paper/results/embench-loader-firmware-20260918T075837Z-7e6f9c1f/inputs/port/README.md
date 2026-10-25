# ZGTC Embench platform port

This directory is external to the pinned Embench checkout. The reference RTL is read-only. The runner snapshots source bytes and compiles unchanged workload files, unchanged `support/beebsc.c`, the platform files here, and copies of the accepted startup/linker files into a unique results directory. Upstream licenses are retained in each source snapshot. The harness derives from GPL-3.0-or-later `support/main.c` and retains attribution.

Run from PowerShell 7 after the pinned compiler is installed:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    & wsl --distribution Ubuntu-22.04 --exec /usr/bin/python3 -B /mnt/d/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/scripts/run_embench.py --workloads crc32
    if ($LASTEXITCODE -ne 0) { throw 'Inspect the new run directory for the failure' }
} catch {
    Write-Error $_
    exit 1
}
```

Omit `--workloads crc32` to include all 19 locked workloads. The runner records every selected workload including build/memory/verification failures. Unselected workloads remain explicitly listed in `all_workloads`; they are not successful results. `--build-only` is a footprint/build check, not correctness.

Protocol v2 fixes RV32IM/ILP32, GCC distribution, global scaling, warm-up and link policy. The complete commands and library hashes appear in run manifests. The SoC simulation accelerates UART to 32 cycles/bit, as in the historical harness. It uses the accepted memory system and complete cache configuration. UART output follows the measured interval. The model's timestamp convention is not an independent frequency measurement. The physical ILA wrapper is outside this simulation; no complete-system FPGA resources or timing can be inferred from it.

`start_trigger` and `stop_trigger` each take an atomic pair of 64-bit performance snapshots. Both raw deltas span the same interval, including start-snapshot reads and hook call overhead. No guessed subtraction is applied. `finish_benchmark` requires verifier return exactly 1 and waits for UART FIFO plus serializer idle before publishing terminal status. UART bit 0 indicates FIFO capacity; bit 1 indicates idle. Verification return -1 is rejected. Exceptions, assertions, runtime exits, simulator timeouts and incorrect verification fail visibly.

Protocol v3 keeps 64 KiB total memory and uses a uniform 16 KiB stack partition. The runner retains the original linker bytes and records its single reservation change in the input snapshot. Newlib heap growth stops at the stack partition. The simulation-only observer checks committed SP bounds after platform initialization, records minimum SP, checks every cycle/retirement counter increment, and requires UART measurements to agree with atomic pre-edge snapshots. This strengthens simulation validation; it is not a physical stack or board test. Results remain functional smoke tests and raw RTL observations, not official Embench scores or board evidence.
