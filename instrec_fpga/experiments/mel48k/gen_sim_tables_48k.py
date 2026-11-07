"""48 kHz simulation tables for tb_mel_engine_48k (RTL COO-swap validation).

Generates, under build/sim/mel_48k/ (the sim run cwd is instrec_fpga/, so
the TB and the mel_engine COO_HEX_FILE override address the tables with
project-root-relative paths, exactly like the 44.1 kHz mel case):

  pcm.hex          132096 s16 samples of a deterministic 48 kHz mix
                   (440 Hz full-scale sine + seeded white noise, both
                   built with the experiments/mel48k/run_check.py recipe:
                   seed 20261104, 3 s pre-cut then windowed to 132096)
  golden_feat.hex  16512 golden feature bytes, feat.T.reshape(-1), i.e.
                   line index = frame*64 + mel (the engine export index;
                   golden feat is (mel=64, frame=258) so the transpose is
                   REQUIRED -- see the tb_mel_engine.sv T35 note)
  mel_coo_48k.hex  byte copy of scripts/outputs/mel_coo_48k.hex (65 offset
                   words + 1962 entries); hann_q15 / log2_lut are sampling
                   rate invariants and stay src/mel/*.hex

The golden truth source is scripts/golden_pipeline.run_mel_pipeline on
scripts/outputs/mel_tables_48k.json (bit-level, 0 LSB vs float math).

Usage (from instrec_fpga/):  python experiments/mel48k/gen_sim_tables_48k.py
Called automatically by sim/run_sim.py case "mel_48k" (prepare hook).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]          # instrec_fpga/
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import golden_pipeline as gp   # noqa: E402 (path-injected module)

SR_48K = 48000
TABLES_48K = SCRIPTS_DIR / "outputs" / "mel_tables_48k.json"
COO_HEX_48K = SCRIPTS_DIR / "outputs" / "mel_coo_48k.hex"
OUT_DIR = ROOT / "build" / "sim" / "mel_48k"

RNG_SEED = 20261104            # same seed as experiments/mel48k/run_check.py
N_FULL_SEC = 144000            # 3 s of audio at 48 kHz (pre-cut)
FULL_SCALE = 32767
SINE_FREQ = 440.0


def synth_pcm() -> np.ndarray:
    """440 Hz sine + seeded white noise, half-power mix, int16 window.

    The sine and the noise are generated exactly like run_check.py
    synth_signals(); the mix (both halves averaged, rounded) keeps every
    sample inside int16 while exciting the whole 0..24 kHz band, so the
    48 kHz COO table (whose high-frequency rows differ from the 44.1 kHz
    one, fmax 24000 vs 22050) is actually exercised -- a pure 440 Hz
    sine would leave those rows on the noise floor.
    """
    t = np.arange(N_FULL_SEC, dtype=np.float64) / SR_48K
    sine = np.round(np.sin(2.0 * np.pi * SINE_FREQ * t) * FULL_SCALE)
    rng = np.random.default_rng(RNG_SEED)
    noise = rng.integers(-FULL_SCALE, FULL_SCALE + 1, size=N_FULL_SEC)
    mix = np.round((sine + noise) / 2.0)
    return np.asarray(mix[: gp.WINDOW_SAMPLES], dtype=np.int16)


def write_hex(path: Path, values, digits: int) -> None:
    """One value per line, zero padded, upper case ($readmemh format)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mask = (1 << (4 * digits)) - 1
    fmt = "{0:0" + str(digits) + "X}"
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        handle.write("\n".join(fmt.format(int(v) & mask) for v in values))
        handle.write("\n")


def main() -> int:
    tables = gp.load_mel_tables(TABLES_48K)
    params = tables["params"]
    if int(params["sr"]) != SR_48K:
        raise SystemExit("table params.sr != 48000: %r" % params["sr"])

    pcm = synth_pcm()
    # The 48 kHz frontend pairs with the native 48 kHz INT8 model contract
    # (deploy/medley_48k): zp_in 47 / inv_s_in 236403274.  Fall back to the
    # module default when that contract is absent (legacy experiments).
    contract_48k = SCRIPTS_DIR / "outputs" / "medley_48k" / "layer_contract.json"
    if contract_48k.is_file():
        import json
        qs = json.loads(contract_48k.read_text(encoding="utf-8"))["quant_stub_input_contract"]
        res = gp.run_mel_pipeline(pcm, tables, inv_s_in=qs["inv_s_in"], zp_in=qs["zp_in"])
    else:
        res = gp.run_mel_pipeline(pcm, tables)
    feat = res["feat"]                              # (64, 258) uint8
    if feat.shape != (gp.N_MELS, gp.N_FRAMES):
        raise SystemExit("unexpected feat shape %r" % (feat.shape,))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_hex(OUT_DIR / "pcm.hex", pcm.view(np.uint16), 4)
    # Transpose: golden is (mel, frame); the TB/engine index is
    # frame*64 + mel, so the flattened table must be frame-major.
    write_hex(OUT_DIR / "golden_feat.hex", feat.T.reshape(-1), 2)
    shutil.copy2(COO_HEX_48K, OUT_DIR / "mel_coo_48k.hex")

    print("[mel48k-sim] pcm  : %s (%d samples, sine+noise mix, seed %d)"
          % (OUT_DIR / "pcm.hex", len(pcm), RNG_SEED))
    print("[mel48k-sim] golden: %s (feat.T frame-major, min %d max %d mean %.2f)"
          % (OUT_DIR / "golden_feat.hex", feat.min(), feat.max(),
             float(feat.mean())))
    print("[mel48k-sim] coo  : %s (%d bytes)"
          % (OUT_DIR / "mel_coo_48k.hex",
             (OUT_DIR / "mel_coo_48k.hex").stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
