# Audio input and board acceptance (2026-11-02)

Current delivery remains the original eight-class recognizer, by the user's
latest decision. The user has not connected an audio source.

## Implemented input

The FPGA generates BCK and LRCK; the source must be an I2S slave transmitter.
The implemented Philips stream is signed 16-bit stereo with 16 BCK periods per
channel, 32 BCK per stereo frame, LRCK approximately 44.1 kHz and BCK 1.4112 MHz.
This is not a 32-bit-slot/64-BCK receiver. The data source changes SD on falling
BCK edges; the receiver samples rising edges with the Philips one-bit offset.
Simulation `i2s_capture` covers real serial waveforms rather than internal
receiver phase assumptions. `audio_fifo` covers capacity, overflow saturation,
wrapping, asynchronous clocks and reset. Physical signal integrity and source
compatibility still need a connected device.

| FPGA signal | Direction | FPGA ball | Core net / bottom-board logical route |
| --- | --- | --- | --- |
| i2s_bck | output | U20 | L6_G2_14N_DQS / FMC_LPC_LA07_N |
| i2s_lrck | output | T20 | L6_G2_14P_DQS / FMC_LPC_LA07_P |
| i2s_sd | input | V16 | L6_G3_23P / FMC_LPC_LA03_P |

The constraints select 3.3-V LVCMOS. These are expansion signals, not an
onboard analog microphone/line input. The bottom-board HDMI receiver MS7200
does expose a separate RX I2S path, but this design does not connect that path
as an audio receiver. Feeding HDMI IN would require a separate slave-clock
capture/configuration integration; it cannot be claimed to work today.

Routes were checked against the 100Pro+ core schematic page 6 and bottom-board
schematic page 9, including a rendered schematic inspection; MS7200 audio
outputs are on bottom schematic page 5. Source hashes and extracted evidence
are recorded in `reports/audio_pin_review_20261102.json`.

## What has passed and what remains

The board has accepted the 691040-byte legacy weight image in 2700 UART frames
with `WOK FA0D5236`, and the CPU has reported six NPU completions in a 12-second
capture. This proves weight transfer/readback and observed inference/control
progress on the diagnostic bitstream. It does not prove recognition accuracy
for an acoustic input, or timing closure.

A subsequent reflash of the same diagnostic image failed weight reload at frame
814, and the user confirmed HDMI no signal. It has been replaced on the board
by the fixed display demo; the user confirmed its colorbars and UI both work.
The earlier transfer/completion evidence remains historical, not proof of the
current full system state. See `reports/full_system_reflash_20261102_1614.json`
and `reports/display_fallback_restore_20261102_1620.json`.

Complete audio acceptance requires a compatible source, known instrument test
clips, correct PCM capture, Mel/golden comparison, NPU results and corresponding
HDMI bars. Record input identity, sample rate, slot format, bitstream and weight
hashes with the result. The diagnostic 489EF753 bitstream still has negative
setup/recovery margins; use the final timing report to assess its replacement.
