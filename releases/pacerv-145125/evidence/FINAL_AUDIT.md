# Independent final audit

Status: PASS

Command: python.exe D:\AAAFPGA\ZGTC_RISC_CPU\pds_minimal_blink_200h\pacerv_h3_optimization\evidence\continuation_20261117\final_audit\audit.py
Input: frozen EXPERIMENT.json, selected V0/V1 RUN/BUILD/UART receipts, all cf*-physical*/BUILD_RESULT.json, selected physical inputs/reports/bitstream, prior archive receipts.
Exit status: 0

Frozen baseline hashes: 182/182 matched.
Common simulation and physical RTL: 17/17 byte-identical.
Core SHA256: 5e81f9c56246e502b43c6a48c14342dbb16ac437788ac01d00a482d9a06ca84b
Bitstream SHA256: 418632ab9c52a72bc42ec6ba140c78bd54efb335be9b6784f4356ed07cc172b3
Firmware SHA256: 941041b71bd0b8a3075bd3470fdd566605492f3ceb21ba8faea677dd230bc0cf

| Run | cycles | CoreMark/MHz | seconds | CRCs |
|---|---:|---:|---:|---|
| cf4-loadsimple-tune5-i6000-V0 | 1708737607 | 3.511364164644 | 11.774247077 | 0xe714 / 0x1fd7 / 0x8e3a / 0xa14c |
| cf4-loadsimple-tune5-i6000-V1 | 1709422750 | 3.509956796819 | 11.778968131 | 0xe3c1 / 0x0747 / 0x8d84 / 0x18e1 |

Both runs pass 6000 iterations, ten-second duration, UART/observer cycle agreement, expected CRCs, firmware/source hashes and zero simulator exit status.

| Physical build | status | slow setup ns |
|---|---|---:|
| cf2-physical-frontend-flat-local-s1 | completed_timing_fail | -0.741 |
| cf4-physical-loadsimple-tune5-local-s1 | completed_timing_fail | -0.234 |
| cf4-physical-loadsimple-tune5-local-s2 | completed_timing_fail | -0.135 |
| cf4-physical-loadsimple-tune5-local-s3 | completed_timing_fail | -0.044 |
| cf4-physical-loadsimple-tune5-local-s4 | completed_timing_fail | -0.056 |
| cf4-physical-loadsimple-tune5-local-s5 | completed_timing_fail | -0.150 |
| cf4-physical-loadsimple-tune5-local-s6 | completed_timing_fail | -0.116 |
| cf4-physical-loadsimple-tune5-local-s7 | completed_timing_fail | -0.194 |
| cf4-physical-loadsimple-tune5-local-s8 | completed_timing_fail | -0.125 |
| cf5-physical-cache-hit-fanout-local-s1 | completed_timing_fail | -0.799 |
| cf6-physical-frontend-range-tune5-local-s1 | completed_timing_fail | -0.102 |

Selected seed 3: 145.125 MHz configured, 0.150 ns uncertainty, slow setup -0.044 ns, TNS -0.086 ns, 3 failing endpoints. Package must retain experimental timing-failed status.
Other nine timing categories pass. Full report, input and bitstream hashes checked for all listed new physical builds.

Existing archives retain the recorded hashes:
- PaceRV_H6_LoadALU_145125_Experimental.zip: 3b86503bf0a5ebc53b4bada6d0bff3d9928792c33816102668dd014fa33bb8be (1181456 bytes)
- PaceRV_Loop16_145125_Verified.zip: fd144bef0d634246a9824bf259bf6fa6aebbe4c272936a4157d1bb110dd03228 (1138478 bytes)

Windows process check: []
WSL process check: {"native_benchmark_processes": []}
Process commands, literal outputs, stderr and exit statuses appear in FINAL_AUDIT.json.

Package verification command: D:\Anaconda\python.exe D:\AAAFPGA\ZGTC_RISC_CPU\pds_minimal_blink_200h\pacerv_h3_optimization\scripts\followup-packaging\verify_package.py --folder D:\AAAFPGA\ZGTC_RISC_CPU\pds_minimal_blink_200h\pacerv_h3_optimization\optimized_releases\PaceRV_H6_SelectiveLoad_145125_Experimental
Literal output: PACKAGE_VERIFY_PASS {"bitstream_sha256": "418632ab9c52a72bc42ec6ba140c78bd54efb335be9b6784f4356ed07cc172b3", "common_rtl": 17, "files": 297, "timing_pass": false, "v0_coremark_per_mhz": 3.5113641646443847, "v1_coremark_per_mhz": 3.509956796819277}
Exit status: 0

Package verification command: D:\Anaconda\python.exe D:\AAAFPGA\ZGTC_RISC_CPU\pds_minimal_blink_200h\pacerv_h3_optimization\scripts\followup-packaging\verify_package.py --zip D:\AAAFPGA\ZGTC_RISC_CPU\pds_minimal_blink_200h\pacerv_h3_optimization\optimized_releases\PaceRV_H6_SelectiveLoad_145125_Experimental.zip
Literal output: PACKAGE_VERIFY_PASS {"bitstream_sha256": "418632ab9c52a72bc42ec6ba140c78bd54efb335be9b6784f4356ed07cc172b3", "common_rtl": 17, "files": 297, "timing_pass": false, "v0_coremark_per_mhz": 3.5113641646443847, "v1_coremark_per_mhz": 3.509956796819277}
Exit status: 0

Board status: selected new bitstream has not been programmed or measured on a live board.
This audit changes only its own evidence files; frozen inputs, RTL, firmware, earlier releases and root reports remain intact.
