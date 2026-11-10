"""Repeatable board-side readback for the 48 kHz diagnostics.

Implements the host half of DIAG_READBACK_PLAN_20261110:

    'L'                 lock the completed window (audio_sink stops writing)
    'S'                 status line  DIAG win=<n> locked=<0/1> mel_done=<n>
                                     npu_done=<n> logits_valid=<0/1>
    'R' addr len        read `len` bytes from DDR, 256-byte frames back
    'G'                 full 8-lane int32 logit vector as one frame
    'U'                 unlock

Because `len` is 16 bits, long regions are read in 255x256-byte pieces
(65,280 B) so every request stays a 256-byte multiple.

Layout written per capture:
    build/diag/<label>/win<NNNN>/
        pcm.raw       264,192 B   (132,096 x int16, mono lane, little endian)
        feat.bin      16,512 B    (64 x 258 uint8, mel_engine output)
        logits.json   8 x int32 + win/locked/mel_done/npu_done flags
        meta.json     addresses, lengths, sha256 of each file, timestamps

Typical use (one flash, several inputs):
    python scripts/diag_dump.py --label silence
    python scripts/diag_dump.py --label tone200 --play build/tone_200.wav
    python scripts/diag_dump.py --label tone6k  --play build/tone_6k.wav
    python scripts/diag_dump.py --label music   --play build/montage_20s_12s.wav
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import i2s_capture as cap  # noqa: E402  (crc16_ccitt + device resolution + player)

# DDR map (must match the RTL/plan)
PCM_LASE = 0x000000
PCM_WIN_STRIDE = 0x042000          # 264 KB per window (WIN_BYTES / PCM_WIN_STRIDE)
PCM_WIN_BYTES = 264192             # 132,096 frames x 2 B (single lane)
FEAT_BASE = 0x00200000
FEAT_BYTES = 16512
MAX_CHUNK = 255 * 256              # 65,280 B per 'R'

SOF = b'\xAA\x55'


def read_exact(ser, n, timeout=2.0):
    buf = b''
    t0 = time.time()
    while len(buf) < n and time.time() - t0 < timeout:
        chunk = ser.read(n - len(buf))
        if chunk:
            buf += chunk
    return buf


def read_frame(ser, timeout=3.0):
    """Read one 0xAA55 frame: seq[2] len[2] payload[len] crc[2]."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        head = ser.read(2)
        if len(head) < 2:
            continue
        if head != SOF:
            continue
        body = read_exact(ser, 4, timeout)
        if len(body) < 4:
            return None
        seq = body[0] | (body[1] << 8)
        ln = body[2] | (body[3] << 8)
        payload = read_exact(ser, ln, max(timeout, ln / 8000.0))
        crc_b = read_exact(ser, 2, timeout)
        if len(payload) < ln or len(crc_b) < 2:
            return None
        crc_rx = crc_b[0] | (crc_b[1] << 8)
        crc_calc = cap.crc16_ccitt_false(body + payload)
        if crc_rx != crc_calc:
            print('  frame seq=%d crc mismatch (got %04x want %04x)' %
                  (seq, crc_rx, crc_calc))
            return None
        return seq, ln, payload
    return None


def read_status(ser):
    ser.reset_input_buffer()
    ser.write(b'S')
    deadline = time.time() + 3.0
    line = b''
    while time.time() < deadline:
        chunk = ser.read(256)
        if chunk:
            line += chunk
            if b'\n' in line:
                break
    text = line.decode('ascii', errors='replace')
    m = re.search(r'DIAG win=(\d+) locked=(\d) mel_done=(\d+) npu_done=(\d+) logits_valid=(\d)', text)
    if not m:
        raise RuntimeError('status line not understood: %r' % text)
    return {
        'win': int(m.group(1)), 'locked': int(m.group(2)),
        'mel_done': int(m.group(3)), 'npu_done': int(m.group(4)),
        'logits_valid': int(m.group(5)),
    }


def read_ddr(ser, addr, length):
    """Read `length` bytes from DDR through 'R' frames."""
    out = bytearray()
    off = 0
    while off < length:
        chunk = min(MAX_CHUNK, length - off)
        chunk -= chunk % 256
        if chunk == 0:
            chunk = 256
        ser.reset_input_buffer()
        ser.write(b'R')
        ser.write((addr + off).to_bytes(4, 'little'))
        ser.write(chunk.to_bytes(2, 'little'))
        frames = chunk // 256
        for f in range(frames):
            fr = read_frame(ser)
            if fr is None:
                raise RuntimeError('read frame %d/%d failed at 0x%08x' %
                                   (f, frames, addr + off))
            seq, ln, payload = fr
            out.extend(payload[:ln])
            ser.write(b'K')          # flow control
            time.sleep(0.002)
        off += chunk
    return bytes(out[:length])


def read_logits(ser):
    ser.reset_input_buffer()
    ser.write(b'G')
    fr = read_frame(ser)
    if fr is None:
        raise RuntimeError('logits frame failed')
    seq, ln, payload = fr
    ser.write(b'K')
    vals = [int.from_bytes(payload[i * 4:(i + 1) * 4], 'little', signed=True)
            for i in range(8)]
    return vals


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--label', required=True)
    ap.add_argument('--play', default=None, help='WAV to play on the Realtek endpoint')
    ap.add_argument('--lead', type=float, default=1.0)
    ap.add_argument('--wait-win', type=float, default=6.0,
                    help='seconds to wait for a fresh window before locking')
    ap.add_argument('--no-lock', action='store_true', help='read without locking')
    args = ap.parse_args(argv)

    import serial
    ser = serial.Serial(args.port, 115200, timeout=0.5)
    player = None
    try:
        if args.play:
            dev = cap.resolve_play_device()
            print('play device =', dev)
            player = cap.start_playback(args.play, dev)
            time.sleep(args.lead)

        # Wait for a window to complete, then lock it.
        t0 = time.time()
        st = read_status(ser)
        while st['win'] == 0 and time.time() - t0 < args.wait_win:
            time.sleep(0.5)
            st = read_status(ser)
        if not args.no_lock:
            ser.write(b'L')
            time.sleep(0.05)
        st = read_status(ser)
        print('status:', st)
        win = st['win']

        pcm_base = PCM_LASE + (PCM_WIN_STRIDE if (win & 1) else 0)
        print('reading pcm @0x%08x (%d B)' % (pcm_base, PCM_WIN_BYTES))
        pcm = read_ddr(ser, pcm_base, PCM_WIN_BYTES)

        print('reading feat @0x%08x (%d B)' % (FEAT_BASE, FEAT_BYTES))
        feat = read_ddr(ser, FEAT_BASE, FEAT_BYTES)

        print('reading logits')
        logits = read_logits(ser)

        if not args.no_lock:
            ser.write(b'U')
            time.sleep(0.05)
    finally:
        ser.close()
        if player is not None:
            cap.stop_playback(player)

    outdir = ROOT / 'build' / 'diag' / args.label / ('win%04d' % win)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / 'pcm.raw').write_bytes(pcm)
    (outdir / 'feat.bin').write_bytes(feat)
    (outdir / 'logits.json').write_text(json.dumps(
        {'win': win, 'logits_int32': logits, **st}, indent=2), encoding='utf-8')

    import numpy as np
    a = np.frombuffer(pcm, dtype='<i2')
    meta = {
        'label': args.label, 'timestamp': datetime.now().isoformat(timespec='seconds'),
        'status': st,
        'pcm': {'addr': pcm_base, 'bytes': len(pcm), 'sha256': sha256_bytes(pcm),
                'std': float(a.std()), 'min': int(a.min()), 'max': int(a.max())},
        'feat': {'addr': FEAT_BASE, 'bytes': len(feat), 'sha256': sha256_bytes(feat),
                 'min': int(np.frombuffer(feat, np.uint8).min()),
                 'max': int(np.frombuffer(feat, np.uint8).max()),
                 'mean': float(np.frombuffer(feat, np.uint8).mean())},
        'logits_int32': logits,
    }
    (outdir / 'meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print('saved:', outdir)
    print('  pcm std=%.1f  feat mean=%.2f  logits=%s' %
          (meta['pcm']['std'], meta['feat']['mean'], logits))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())