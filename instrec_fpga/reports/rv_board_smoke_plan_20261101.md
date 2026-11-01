# RV board smoke plan

This is an offline preparation package. No downloader, serial port, JTAG
server, `cdt_cfg`, or `cdt_js` process was accessed. A board PASS requires a
later run of `scripts/board_check.py` with its JSON evidence.

## Sequence after a new RV bitstream is available

1. Program the bitstream with the existing `board_check.py`; open the UART
   before programming and reuse the single existing JTAG server. Require
   `INSTREC BOOT`, `DDR3 SELFTEST...`, `DDROK`, `RUN`, `RV32 BOOT`,
   `RV32 MMIO OK`, `RV32 ISA OK`, `RV32 BENCH`, `DDR OK STS 0x00000001` and
   `NPU GO`. Missing output or a downloader disappearance is a board failure.
2. Wait for `RUN`, DDR self-test completion and the CPU ROM's one `NPU_CTRL=1`
   write. The CPU request is queued until `mel_npu_start` and the launch gate
   sees `ddr_init_done`, `weight_ok`, no loader/NPU/native fault, and an idle
   M1 owner. Current ROM does not request inference twice.
3. Upload `scripts/outputs/weights_image.bin` at 115200 8N1 with
   `scripts/weight_upload.py`. The loader accepts 2700 data frames of up to
   256 bytes, then an empty `seq=0xffff` end frame. Require `K` per data frame
   and `WOK FA0D5236`; any `N`/`WERR` fails the upload. The expected SHA-256 is
   `19a74dbec29d3a0f16ab06dc30f70312849977de0c6b345710b046b1908f5d7a`.
4. For the current top, I2S input is hard-tied to zero. Therefore no real
   instrument audio is available: a complete Mel window requires 132096 left
   samples, about 2.995 seconds at 44.1 kHz, and the expected feature stream is
   a model-only silence frame of uint8 value 49. A real board run must capture
   the resulting CPU `NPU top1=<n> last_class=<n> last_p=<n> c=<cycles>` line;
   the offline model's class/probability is not board evidence.
5. Require the CPU result line, then verify the firmware clears the sticky
   result via `NPU_CTRL=2`: status must no longer report `ST_PROBS`/`DONE`, and
   no timeout/trap line may appear. Save the fixed-key board JSON and UART
   capture. `NPU top1` is the argmax indicator; `last_class`/`last_p` are the
   streamed class and percentage snapshot.

## Offline package and limits

`build/rv_board_smoke_offline/manifest.json` and
`reports/rv_board_smoke_offline_20261101.json` record the image SHA, 2701
framed packets, every CRC check, the expected folded readback digest, and a
frame-major silence feature reference. `weights_wire_frames.bin` is useful for
codec inspection only; it is explicitly not a valid unpaced upload stream,
because the board requires an ACK before the next frame.

The package predicts silence behavior with the integer golden model only. It
does not prove DDR PHY training, physical UART/JTAG, weight readback, Mel
timing, real audio acquisition, CDC, routing, or board inference. The actual
audio/I2S input is unavailable in this top because `i2s_sd` is tied low.
