#!/usr/bin/env python3
"""Inject a 132,096-sample window over UART and run inference on the board.

Why
---
Everything downstream of DDR3 (mel -> standardize -> quantize -> NPU) was proven
bit-exact against the golden reference, but the only way to get audio in was the
analogue loop: PC DAC -> 3.5 mm -> PCM1808 -> I2S.  That loop is the flakiest
part of the bench (frequency halving when a wire is loose, minutes-long dropouts,
a muted endpoint that silently records silence).  This tool removes it.

How
---
The bitstream gives the single framed loader a base-address select (inject_sel)
plus three diag commands:

    'I'  injection mode: route UART bytes to that loader, weight loader off
    'X'  leave injection mode
    'T'  start mel once on the injected window (base 0x0)

So the sequence is: lock the audio writer ('L'), push 264,192 B (1032 frames of
the same CRC-framed protocol the weight upload uses), trigger ('T'), read the
logits ('G'), unlock ('U').

Because the audio writer is frozen and mel is started explicitly, the window is
exactly what was sent - no ping-pong race, no analogue colouring.

Usage
-----
    python scripts/inject_audio.py --wav clip.wav
    python scripts/inject_audio.py --wav clip.wav --golden      # compare with golden
    python scripts/inject_audio.py --wav clip.wav --repeat 3    # 3 windows
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import board_accuracy as ba                      # noqa: E402
import diag_dump as dd                           # noqa: E402
import weight_upload as wu                       # noqa: E402

WINDOW = 132096
IMAGE_BYTES = WINDOW * 2                         # 264,192 = 1032 x 256


def load_window(path: Path, peak_dbfs: float = -1.0) -> np.ndarray:
    """Read any wav, resample to 48 kHz, peak-normalise, tile to one window."""
    try:
        pcm48 = ba.prep_clip(path, peak_dbfs)
    except Exception:
        from scipy.io import wavfile
        sr, x = wavfile.read(path)
        x = np.asarray(x, dtype=np.float64)
        m = max(abs(float(x.max())), abs(float(x.min())), 1e-9)
        x = np.clip(x / m, -1.0, 1.0) * 32767.0
        x = np.round(x).astype(np.int16)
        if x.ndim == 2:
            x = x[:, 0]
        pcm48 = ba.resample_to_48k(x, sr)
        peak = float(np.abs(pcm48).max()) or 1.0
        pcm48 = np.clip(pcm48 * (32767.0 * (10.0 ** (peak_dbfs / 20.0)) / peak),
                        -32768, 32767).round().astype(np.int16)
    return np.tile(pcm48, int(np.ceil(WINDOW / max(1, pcm48.size))))[:WINDOW]


def drain(ser, settle: float = 0.12) -> None:
    """Consume command ACKs ('K') so they cannot be mistaken for upload ACKs.

    'U'/'L'/'I'/'X'/'T' each make the diag engine emit a 'K'.  If one is left
    in the buffer when Uploader starts, frame N's ACK is consumed by frame
    N-1 and the trailing 'K' lands in front of the WOK line -> a successful
    upload is reported as FAILED.  Uploader._wait_ack already skips stray
    telemetry bytes, but a *valid* 'K' from an earlier command is different:
    it must be removed before the upload begins.
    """
    time.sleep(settle)
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.02)


def wait_logits(ser, timeout=15.0) -> list[int]:
    """Poll 'S' until the NPU has produced logits, then read 'G'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = dd.read_status(ser)
        if st.get("logits_valid"):
            return dd.read_logits(ser)
        time.sleep(0.3)
    return dd.read_logits(ser)


def inject_window(ser, pcm: np.ndarray, progress=None, timeout: float = 15.0):
    """Push one 132096-sample window over an EXISTING serial port and infer.

    Returns ``(wok_text, logits, frames, retransmits)``.  Split out from
    ``main()`` so the Tkinter GUI can reuse its single worker-owned serial
    handle instead of opening a competing port.  The caller is responsible for
    uploading the weights once before the first injection.
    """
    image = pcm.astype("<i2").tobytes()
    assert len(image) == IMAGE_BYTES, len(image)

    ser.write(b"U")            # drop any stale lock
    time.sleep(0.05)
    ser.write(b"L")            # freeze audio_sink: nothing may overwrite DDR
    time.sleep(0.05)
    ser.write(b"I")            # injection mode on (loader base -> 0x0)
    drain(ser)                 # eat the three 'K' ACKs

    # Software recovery for a wedged loader.  If a PREVIOUS upload aborted
    # mid-image (a lost ACK, a CRC retry budget exhausted, a crashed script),
    # frame_cnt is stuck at some non-zero value and img_done was never set:
    # every new image then NAKs its first seq=0 frame until the FPGA is
    # re-flashed.  Sending a bare END frame makes the loader finish its
    # read-back (WOK), reach S_FIN and set img_done, so the next SOF lazily
    # clears frame_cnt.  On a clean loader this is a harmless no-op that
    # returns "WOK 00000000".
    ser.write(wu.build_frame(wu.END_SEQ, b""))
    deadline = time.time() + 8.0
    reply = b""
    while time.time() < deadline and b"\n" not in reply:
        chunk = ser.read(64)
        if chunk:
            reply += chunk
    drain(ser)

    up = wu.Uploader(ser, image, timeout=1.0, retries=3, progress=progress)
    text = up.run()
    if not text.startswith("WOK"):
        drain(ser)
        ser.write(b"X")
        ser.write(b"U")
        raise RuntimeError("upload rejected: %r" % text[:60])

    drain(ser)
    ser.write(b"X")            # back to normal command routing
    time.sleep(0.05)
    ser.write(b"T")            # start mel on the injected window
    drain(ser)
    logits = wait_logits(ser, timeout)
    # Leave the window frozen so the exported dB spectrum at 0x200000 stays
    # valid until the GUI has read it.  main() unlocks at the very end.
    return text.strip(), logits, up.sent_frames, up.retransmits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wav", required=True)
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--repeat", type=int, default=1, help="windows to inject")
    ap.add_argument("--golden", action="store_true",
                    help="also run the golden pipeline on the injected window")
    ap.add_argument("--keep-lock", action="store_true",
                    help="leave the audio writer frozen afterwards")
    args = ap.parse_args(argv)

    import serial

    wav = Path(args.wav)
    pcm = load_window(wav)
    print("clip   : %s" % wav.name)
    print("window : %d samples (%d B, %d frames of 256 B)" % (WINDOW, IMAGE_BYTES, IMAGE_BYTES // 256))
    print("level  : peak %d  rms %.0f" % (int(np.abs(pcm).max()), float(pcm.std())))

    ser = serial.Serial(args.port, 115200, timeout=0.5)
    time.sleep(0.2)
    ser.reset_input_buffer()

    for run in range(args.repeat):
        t0 = time.time()
        text, logits, frames, retrans = inject_window(
            ser, pcm,
            progress=lambda i, n: print("      %4d/%d" % (i, n), end="\r", flush=True))
        print("      upload OK in %.1f s (%d frames, %d retransmits)" % (
            time.time() - t0, frames, retrans))
        print("   run %d  board logits = %s   top1=%d"
              % (run, logits, int(np.argmax(logits))))

        if args.golden:
            import golden_pipeline as gp
            tables = gp.load_mel_tables(SCRIPTS / "outputs" / "mel_tables_48k.json")
            contract = gp.load_layer_contract(SCRIPTS / "outputs" / "medley_48k" / "layer_contract.json")
            weights = gp.load_weights_from_image(contract, SCRIPTS / "outputs" / "medley_48k" / "weights_image.bin")
            rec = contract.get("quant_stub_input_contract", contract)
            feat = gp.run_mel_pipeline(pcm, tables, inv_s_in=int(rec["inv_s_in"]),
                                       zp_in=int(rec["zp_in"]))["feat"]
            out = gp.npu_forward(feat, contract, tables["exp_lut"], weights=weights)
            gl = [int(v) for v in out["logits"]]
            same = gl == logits
            print("        golden logits = %s   top1=%d   %s"
                  % (gl, int(out["top1"]), "IDENTICAL" if same else
                     "max|d|=%d" % max(abs(a - b) for a, b in zip(gl, logits))))

    if not args.keep_lock:
        ser.write(b"U")
    ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
