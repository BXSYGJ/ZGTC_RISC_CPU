"""One-shot 48 kHz board acceptance: flash -> weights -> play -> read telemetry.

Run after the FTDI downloader is back in PnP:

    python scripts/board_48k_run.py \
        --sbit releases/instrec-48k-diag2-20261107/instrec_48k_diag2.sbit \
        --image scripts/outputs/medley_48k/weights_image.bin \
        --play-wav build/montage_20s_12s.wav --seconds 30

It prints the periodic "DDR3 STS" telemetry decoded as
{overflow byte, window real-frame count, win_id} plus the NPU top1 lines, so
one run decides whether the 19% real-frame rate is an overflow or a
write-side loss (see docs/STATUS.md, 2026-11-07 第十二批).
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import i2s_capture as cap   # noqa: E402  (device resolution + waveOut player)


def run(cmd):
    print('$', ' '.join(str(c) for c in cmd))
    res = subprocess.run([str(c) for c in cmd], cwd=str(ROOT),
                         capture_output=True, text=True, encoding='utf-8',
                         errors='replace')
    print((res.stdout or '')[-1500:])
    return res.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--sbit', required=True)
    ap.add_argument('--image', default='scripts/outputs/medley_48k/weights_image.bin')
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--play-wav', default='build/montage_20s_12s.wav')
    ap.add_argument('--seconds', type=float, default=30.0)
    args = ap.parse_args()

    if not run([sys.executable, 'scripts/board_check.py', '--sbit', args.sbit]):
        print('flash/boot FAIL')
        return 5
    if not run([sys.executable, 'scripts/weight_upload.py', '--image', args.image]):
        print('weight upload FAIL')
        return 6

    dev = cap.resolve_play_device()
    print('play device =', dev)
    player = cap.start_playback(args.play_wav, dev)
    try:
        time.sleep(2.0)
        import serial
        ser = serial.Serial(args.port, 115200, timeout=0.5)
        buf = b''
        t0 = time.time()
        while time.time() - t0 < args.seconds:
            chunk = ser.read(512)
            if chunk:
                buf += chunk
        ser.close()
    finally:
        cap.stop_playback(player)

    text = buf.decode('ascii', errors='replace')
    print('--- DDR3 STS telemetry (overflow | frames | win_id) ---')
    for m in re.finditer(r'DDR3 STS ([0-9A-Fa-f]{8})', text):
        v = int(m.group(1), 16)
        print('  raw=%s overflow=%d frames=%d win_id=%d' %
              (m.group(1), (v >> 24) & 0xFF, (v >> 8) & 0xFFFF, v & 0xFF))
    tops = re.findall(r'top1=(\d+).*?last_p=(\d+)', text)
    if tops:
        print('--- NPU ---')
        print('  rounds=%d distinct_top1=%s last_p=%s' %
              (len(tops), sorted({t[0] for t in tops}), sorted({t[1] for t in tops})))
    else:
        print('  no NPU lines')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
