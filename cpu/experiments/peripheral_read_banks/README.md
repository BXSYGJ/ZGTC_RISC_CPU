# Banked peripheral MMIO read decoder

## Scope

This complete-peripheral candidate changes only the read decoder in `rv32_peripherals.sv`. Two exact substitutions in `change-receipt.json` replace the flat full-address read case with a high-address check, five bank selections and byte-offset cases. All 26 readable addresses, error responses, registered response timing and write-side state updates remain present. GPIO, UART FIFOs and interrupts, software/timer interrupts, the 64-bit timer and all nine performance snapshot words are retained. This is not the earlier peripheral-removal experiment.

The complete-system stage retains the `full_id_relation_mask1` CPU and predictor unchanged; its twenty physical inputs differ from that parent only in `rtl/rv32_peripherals.sv`. The tested peripheral SHA256 is `ACA515C9557035BCDDDB11C92BE50ED32E7F710795FDC56F4E52CDEAE1D1B9B2`, from parent `B61ED1BC98CA4B6375AA27337FB6C68091FBFEBA156495424D71431A6F4630E6`. The inherited GPIO/UART and 42-data / 33-trigger / 1024-sample ILA requirements are unchanged.

## Functional evidence

`test_banked_reads.py` passes three methods and five real compiled fault rejections. The original independent peripheral tests run beside a cycle-by-cycle reference instance: 105281 differential cycles, 55803 checks and 831 backpressure waits. Added coverage includes all 2048 low-address offsets, 10752 high-bit alias reads, two unknown upper-address cases and sixteen distinct snapshots. UART loopback, FIFO full/empty behavior, framing/overrun errors, interrupt control, GPIO edge/pending handling, byte strobes, response stalls and timer rollover are exercised. This is bounded testing, not an exhaustive proof over all internal states.

Source-bound evidence is `build/functional-1205ce4f/manifest.json`, SHA256 `276D7FBE1AF5067F24893B6766B773E95C3560F3E4923469A45A32098A4D7C53`. All generated testbenches, executables, diagnostics and intentional fault failures are retained.

Both complete-SoC short runs pass and their entire UART logs are byte-identical to the immediate parent: V0 3000565 cycles / 2748941 retired / fcaf; V1 3001255 / 2749614 / c64e. Source, firmware, compiler command and physical inputs are bound in `build/v0` and `build/v1`. These ten-iteration results are not long-run performance scores.

## Physical evidence

Ordinary run `20260911-074734-14aad077` is terminal at 151.2 MHz: **9207 post-route LUT / 4352 FF / WNS -0.009 ns**. It fails timing; the native tool generates a bitstream, but the timing auditor rejects the run. Ordinary counts do not include the required complete ILA and cannot be used as the final resource-efficiency denominator.

Actual synthesis shows total LUTs 8753 -> 8709, while the inclusive peripheral hierarchy remains 733 LUT / 635 FF. Peripheral carry LUTs fall from 172 to 163 and LUT7 muxes rise from zero to three. Other hierarchy counts also change despite unchanged CPU RTL. These are observations from separately synthesized complete designs, not proof of a fixed area saving attributable to the peripheral block. The source-bound raw report comparison is `build/synthesis-comparison.json`; nested counts must not be added.

Full ILA `build/ila/peripheral-read-banks-seed1` starts after the ordinary native process terminates, as PDS PID 89184. Actual Inserter verification confirms 42 data / 33 trigger channels and 1024 samples. The source netlist exposes the MEM valid bit at core pipeline_valid[3]; the auditor verifies its register driver before normalizing the historical observation alias. Ten binding/native-mapping methods plus three staging methods pass, recorded in `build/binding-audit-tests.log`. Both PowerShell entry scripts parse successfully. The complete run is now terminal: **9579 total LUT / 5056 FF / WNS -0.071 ns**, four failing setup endpoints and TNS -0.119 ns at 151.2 MHz. The bitstream SHA256 is `F2A5D4C236BE4B249BBE3273D9BB7F442828D7245E8F9056B0121AAC4554E0CA`. Complete area decreases by 53 LUT relative to the immediate parent, but timing fails, so this candidate is rejected.

## Next gates

No long runs or board programming follow this failed complete implementation. The worst path runs from MEM result bit 24 through the byte comparison, signed relation, branch condition and instruction-cache request logic to the read-only cache RAM address: nine levels, 1.737 ns logic and 4.826 ns routing. Other failures follow the same source to the cache state and RAM address. The conditional 9453-LUT target would still require 126 fewer LUTs even if parent performance were preserved; it is not a score assigned to this candidate. No metric-qualified baseline, board image or GitHub state is changed.
