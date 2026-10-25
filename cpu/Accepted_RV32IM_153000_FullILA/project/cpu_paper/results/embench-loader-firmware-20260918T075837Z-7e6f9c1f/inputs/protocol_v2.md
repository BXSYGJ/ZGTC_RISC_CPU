# Evaluation protocol v2 — toolchain amendment, 2026-09-18

## Material Passport

- Origin: inspected local compiler and upstream xPack release documentation.
- Verification status: prospective; this amendment does not claim benchmark correctness.
- Supersedes only the toolchain selection in protocol_v1.md; all other gates remain binding.

The historical bare-metal GCC 10.2.0 installation has no libc/libm or C-library headers. Its original build script explicitly used --without-headers. Keep that installation and all accepted firmware unchanged. For all new Embench and comparative CoreMark firmware, freeze xPack riscv-none-embed GCC 10.2.0-1.2, Linux x64, with its RV32IM/ILP32 libraries. This is a different compiler distribution, not a reproduced historical binary. Rebuild both sides of each new comparison with it. Archived CoreMark firmware may additionally be used for labeled continuity smoke tests.

Archive: xpack-riscv-none-embed-gcc-10.2.0-1.2-linux-x64.tar.gz

SHA-256: d72bdcd1eee41dc5a208a8a03976b70d014510deb5890c9e8738e804ba23f985

[Primary release documentation and checksum](https://xpack-dev-tools.github.io/riscv-none-elf-gcc-xpack/blog/2021/11/11/riscv-none-embed-gcc-v10-2-0-1-2-released/) documents non-compressed RV32IM/ILP32 libraries and requires -mcmodel=medany. Add that flag consistently. Use standard newlib, not a per-workload switch to nano. Preserve archive and license notices. Capture the selected libc, libm, libgcc paths/hashes and the full compiler version. Library optimization is prebuilt and must not be described as project O3 compilation.

Embench compiler flags: -march=rv32im -mabi=ilp32 -mcmodel=medany -msmall-data-limit=0 -std=c11 -O3 -funroll-loops -ffreestanding -fno-builtin -ffunction-sections -fdata-sections -Wall -Wextra. Link with -nostdlib -nostartfiles -Wl,--relax -Wl,--gc-sections, the platform linker script and standard libm/libc/libgcc. No LTO and no compressed instructions. Section collection applies to every workload, not just those that exceed memory. Compile the unchanged pinned workload C files and support/beebsc.c with the external harness in ports/embench. That harness follows pinned support/main.c's sequence and strengthens acceptance to verifier return == 1.

CoreMark retains its documented benchmark-specific definitions and freestanding runtime. Its new compiler identity and medany flag must be bound in a new build manifest. Do not claim that the new flags/compiler reproduce the accepted historical score.

All initial runs remain smoke tests, including successful upstream checks and raw cycle observations. Full benchmark, A/B regression, physical and comparator gates still apply. A missing dependency is recorded as such, not an unsupported workload result.
