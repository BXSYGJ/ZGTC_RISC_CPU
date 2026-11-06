#!/usr/bin/env python3
"""PC-side controller for the board I2S capture flow (top_i2s_capture).

Wire protocol -- the READ-BACK direction of weight_upload.py (same frame
format, opposite data flow):

    PC -> FPGA:
        'C'                    start a capture (the FPGA records the fixed
                               4 s window into DDR3)
        'R' + seq[2 LE]        request data frame `seq`
        'K'                    frame accepted (CRC ok); the FPGA waits for
                               this before sending the next frame

    FPGA -> PC:
        "I2SCAP BOOT" / "I2SCAP DDR OK"   boot banner tokens
        "CAPDONE <frame_cnt>"             capture stored, frame count
        SOF0=0xAA SOF1=0x55 | seq[2] | len[2] | payload[len] | crc16[2]

    Every field little-endian; crc16 is CRC-16/CCITT-FALSE over seq, len
    and payload (poly 0x1021, init 0xFFFF, no reflection, xorout 0) --
    the identical definition of weight_upload.crc16_ccitt_false.

Flow: open UART -> wait for the boot tokens -> optionally start looping
playback of --play-wav via winsound -> sleep --lead seconds -> send 'C'
-> wait for "CAPDONE <n>" -> request frames 0..n-1 ('R'+seq, verify CRC,
ack 'K', one retry per frame on a bad CRC, second failure is fatal) ->
reassemble the payload stream (interleaved {R,L} 16-bit samples) -> write
pcm.raw + capture.wav (48 kHz stereo 16-bit) + manifest.json under
build/i2s_capture/<label>_<timestamp>/ -> print a 12-key JSON summary.

The script is hardware-facing: do NOT run it until the top_i2s_capture
bitstream has been built and programmed. All pure logic is covered by
tests/test_i2s_capture_tools.py without a serial port.

Usage:
  python scripts/i2s_capture.py --port COM5 --seconds 4 \
      --play-wav tests/fixtures/sine_440_full.wav --lead 1.0
  python scripts/i2s_capture.py --port COM5            # no playback,
      # prints "play the source manually" and waits for the boot tokens
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / 'build' / 'i2s_capture'

SOF = b'\xAA\x55'
MAX_PAYLOAD = 256                       # data frames carry 256 B payloads
FRAME_OVERHEAD = 2 + 2 + 2 + 2          # SOF + seq + len + crc16
BOOT_TOKENS = ('I2SCAP BOOT', 'I2SCAP DDR OK')
CAPDONE_PREFIX = 'CAPDONE'

SAMPLE_RATE = 48000
CHANNELS = 2
BYTES_PER_SAMPLE = 2
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE   # 192000
FRAMES_PER_SECOND = BYTES_PER_SECOND // MAX_PAYLOAD            # 750

# Fixed key set of the stdout JSON summary (board_check.py convention:
# downstream tools decide pass/fail from the file/stdout alone).
SUMMARY_KEYS = (
    'port', 'baud', 'seconds', 'label', 'play_wav', 'frame_cnt',
    'frames_received', 'crc_errors', 'retries', 'pcm_bytes',
    'uart_sha256', 'verdict',
)


# ---------------------------------------------------------------------------
# Frame codec (CRC-16/CCITT-FALSE, byte-identical to weight_upload.py).
# ---------------------------------------------------------------------------
def crc16_ccitt_false(data):
    """CRC-16/CCITT-FALSE (init 0xFFFF, poly 0x1021, no reflection).

    Same algorithm as weight_upload.crc16_ccitt_false; kept as an
    independent copy so the two modules cross-check each other in
    tests/test_i2s_capture_tools.py.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_frame(seq, payload):
    """Encode SOF + seq + len + payload + crc16 (weight_upload layout)."""
    if not 0 <= seq <= 0xFFFE:
        raise ValueError(f'seq out of range 0..0xFFFE, got {seq}')
    if not 0 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError(f'payload must be 0..{MAX_PAYLOAD} bytes, got {len(payload)}')
    body = seq.to_bytes(2, 'little') + len(payload).to_bytes(2, 'little') + bytes(payload)
    return SOF + body + crc16_ccitt_false(body).to_bytes(2, 'little')


def parse_frame(frame):
    """Decode and CRC-verify a data frame; raise ValueError on any defect.

    Returns (seq, payload). Accepts exactly one frame (no trailing bytes).
    """
    frame = bytes(frame)
    if len(frame) < FRAME_OVERHEAD:
        raise ValueError(f'short frame: {len(frame)} bytes')
    if frame[:2] != SOF:
        raise ValueError('missing SOF 0xAA 0x55')
    seq = int.from_bytes(frame[2:4], 'little')
    length = int.from_bytes(frame[4:6], 'little')
    if length > MAX_PAYLOAD:
        raise ValueError(f'payload length {length} > {MAX_PAYLOAD}')
    if len(frame) != FRAME_OVERHEAD + length:
        raise ValueError(f'frame length {len(frame)} != header + payload {length}')
    payload = frame[6:6 + length]
    crc_rx = int.from_bytes(frame[6 + length:8 + length], 'little')
    crc_calc = crc16_ccitt_false(frame[2:6 + length])
    if crc_rx != crc_calc:
        raise ValueError(f'CRC mismatch on seq {seq}: got 0x{crc_rx:04X}, want 0x{crc_calc:04X}')
    return seq, payload


def expected_frames(seconds):
    """Payload frames a `seconds` long 48 kHz stereo s16 capture yields."""
    return int(seconds * BYTES_PER_SECOND) // MAX_PAYLOAD


def reassemble(payloads):
    """Concatenate ordered frame payloads into the raw PCM byte stream."""
    return b''.join(bytes(p) for p in payloads)


# ---------------------------------------------------------------------------
# Output artifacts.
# ---------------------------------------------------------------------------
def write_wav(path, pcm_bytes, rate=SAMPLE_RATE, channels=CHANNELS, sampwidth=2):
    """Write raw little-endian s16 PCM bytes as a WAV file."""
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(bytes(pcm_bytes))
    return Path(path)


def write_manifest(path, manifest):
    """Write the manifest as UTF-8 JSON without a BOM (LF endings)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return target


def read_manifest(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Playback (winsound with a manual-playback fallback).
# ---------------------------------------------------------------------------
PLAY_DEVICE = 4              # waveOut index of the Realtek endpoint (PCM1808 line-in)
SND_FILENAME = 0x00020000    # winsound flag values (module attrs when
SND_ASYNC = 0x00000001       # winsound is importable)
SND_LOOP = 0x00000008
SND_PURGE = 0x00000040


class WaveOutPlayer:
    """Play a WAV on a SELECTED render endpoint (waveOut device index).

    winsound always follows the Windows default endpoint, which on this host
    is the USB headset (NICEHCK), not the Realtek line-out that feeds PCM1808.
    The capture chain therefore requires an explicit device id plus a full
    endpoint volume; those two together were the silent-capture root cause.
    """

    def __init__(self, path, device_id, loop=True):
        import ctypes
        import ctypes.wintypes as wt
        import wave

        self.ctypes = ctypes
        self.wt = wt
        self.winmm = ctypes.WinDLL('winmm')
        self.loop = loop
        self.device_id = int(device_id)
        w = wave.open(str(path), 'rb')
        self.sr = w.getframerate()
        self.ch = w.getnchannels()
        self.sw = w.getsampwidth()
        self.data = w.readframes(w.getnframes())
        w.close()
        self.handle = wt.HANDLE()
        self.hdr = None
        self.started = False

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [('wFormatTag', wt.WORD), ('nChannels', wt.WORD),
                        ('nSamplesPerSec', wt.DWORD), ('nAvgBytesPerSec', wt.DWORD),
                        ('nBlockAlign', wt.WORD), ('wBitsPerSample', wt.WORD),
                        ('cbSize', wt.WORD)]

        class WAVEHDR(ctypes.Structure):
            _fields_ = [('lpData', ctypes.c_char_p), ('dwBufferLength', wt.DWORD),
                        ('dwBytesRecorded', wt.DWORD), ('dwUser', ctypes.c_void_p),
                        ('dwFlags', wt.DWORD), ('dwLoops', wt.DWORD),
                        ('lpNext', ctypes.c_void_p), ('reserved', ctypes.c_void_p)]

        self.WAVEHDR = WAVEHDR
        self.wfmt = WAVEFORMATEX(1, self.ch, self.sr,
                                 self.sr * self.ch * self.sw,
                                 self.ch * self.sw, self.sw * 8, 0)
        try:
            self.winmm.waveOutSetVolume(ctypes.c_void_p(self.device_id),
                                        ctypes.c_uint32(0xFFFFFFFF))
        except Exception:
            pass

    def start(self):
        rc = self.winmm.waveOutOpen(self.ctypes.byref(self.handle), self.device_id,
                                    self.ctypes.byref(self.wfmt), 0, 0, 0)
        if rc != 0:
            raise RuntimeError('waveOutOpen device %d rc=%d' % (self.device_id, rc))
        self.hdr = self.WAVEHDR(self.data, len(self.data), 0, None,
                                0, 0xFFFFFFFF if self.loop else 0, None, None)
        self.winmm.waveOutPrepareHeader(self.handle, self.ctypes.byref(self.hdr),
                                        self.ctypes.sizeof(self.hdr))
        self.winmm.waveOutWrite(self.handle, self.ctypes.byref(self.hdr),
                                self.ctypes.sizeof(self.hdr))
        self.started = True
        return self

    def stop(self):
        if not self.started:
            return
        try:
            self.winmm.waveOutReset(self.handle)
            self.winmm.waveOutClose(self.handle)
        finally:
            self.started = False


def start_playback(wav_path, device_id=None):
    """Start playback and return a player object, or None when unavailable.

    device_id is the waveOut index (4 = Realtek on this host); the module-level
    PLAY_DEVICE default is used when None.
    """
    dev = PLAY_DEVICE if device_id is None else int(device_id)
    try:
        return WaveOutPlayer(wav_path, dev).start()
    except Exception as exc:
        print('waveOut playback unavailable on device %d: %s' % (dev, exc))
        return None


def stop_playback(player):
    """Stop the playback started by start_playback."""
    if player is not None:
        player.stop()


# ---------------------------------------------------------------------------
# UART helpers (streaming, everything read is appended to the raw log).
# ---------------------------------------------------------------------------
class UartLog:
    """Byte sink recording everything the board sent, for the manifest."""

    def __init__(self):
        self.chunks = []

    def feed(self, data):
        if data:
            self.chunks.append(bytes(data))

    @property
    def raw(self):
        return b''.join(self.chunks)


def wait_for_tokens(port, tokens, timeout, log=None, poll=0.05):
    """Read lines until every token substring has been seen.

    Returns (ok, lines): ok is False on timeout, lines holds every decoded
    line seen so far (the caller can report what was missing).
    """
    seen = set()
    lines = []
    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline and len(seen) < len(tokens):
        data = port.read(4096)
        if not data:
            continue
        if log is not None:
            log.feed(data)
        buf.extend(data)
        while b'\n' in buf:
            raw_line, _, rest = bytes(buf).partition(b'\n')
            buf = bytearray(rest)
            text = raw_line.rstrip(b'\r').decode('ascii', 'replace').strip()
            if not text:
                continue
            lines.append(text)
            for token in tokens:
                if token in text:
                    seen.add(token)
    return len(seen) == len(tokens), lines


def wait_for_capdone(port, timeout, log=None):
    """Wait for the 'CAPDONE <frame_cnt>' line; return (frame_cnt, line).

    frame_cnt is None on timeout.
    """
    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = port.read(4096)
        if not data:
            continue
        if log is not None:
            log.feed(data)
        buf.extend(data)
        while b'\n' in buf:
            raw_line, _, rest = bytes(buf).partition(b'\n')
            buf = bytearray(rest)
            text = raw_line.rstrip(b'\r').decode('ascii', 'replace').strip()
            if not text:
                continue
            parts = text.split()
            if parts and parts[0] == CAPDONE_PREFIX and len(parts) >= 2:
                try:
                    return int(parts[1]), text
                except ValueError:
                    pass
    return None, None


class FrameReader:
    """Extract length-delimited frames from the UART byte stream.

    Keeps a residual buffer so a frame split across serial reads is
    reassembled; bytes before a SOF pair (debug prints, boot spam) are
    forwarded to the UartLog and dropped.
    """

    def __init__(self, port, log=None):
        self.port = port
        self.log = log
        self.buf = bytearray()

    def _fill(self, deadline):
        while time.time() < deadline:
            data = self.port.read(4096)
            if data:
                if self.log is not None:
                    self.log.feed(data)
                self.buf.extend(data)
                return True
        return False

    def read_frame(self, timeout):
        """Return one raw frame (bytes) or None on timeout."""
        deadline = time.time() + timeout
        while True:
            # Locate a SOF; log/drop the leading noise bytes.
            idx = bytes(self.buf).find(SOF)
            while idx < 0:
                if self.buf:
                    if self.log is not None:
                        self.log.feed(bytes(self.buf))
                    self.buf.clear()
                if not self._fill(deadline):
                    return None
                idx = bytes(self.buf).find(SOF)
            if idx > 0:
                if self.log is not None:
                    self.log.feed(bytes(self.buf[:idx]))
                del self.buf[:idx]
            # Need the 6-byte header to know the full frame length.
            if len(self.buf) < 6 and not self._fill(deadline):
                return None
            if len(self.buf) < 6:
                continue
            length = int.from_bytes(self.buf[4:6], 'little')
            if length > MAX_PAYLOAD:
                # Bogus length: the "SOF" was coincidental text. Skip one
                # byte and resynchronise.
                if self.log is not None:
                    self.log.feed(bytes(self.buf[:1]))
                del self.buf[:1]
                continue
            total = FRAME_OVERHEAD + length
            while len(self.buf) < total:
                if not self._fill(deadline):
                    return None
            frame = bytes(self.buf[:total])
            del self.buf[:total]
            return frame


def fetch_frame(port, reader, seq, timeout):
    """Send 'R'+seq and read/verify one data frame.

    Returns (payload, crc_failed_once): payload is None on timeout or a
    CRC error (the caller decides whether it was the retry attempt).
    """
    port.write(b'R' + seq.to_bytes(2, 'little'))
    port.flush()
    frame = reader.read_frame(timeout)
    if frame is None:
        return None, False
    try:
        rx_seq, payload = parse_frame(frame)
    except ValueError:
        return None, True
    if rx_seq != seq:
        return None, True
    return payload, False


def run_capture(args):
    """Drive the full board session; returns (exit_code, summary)."""
    summary = {key: None for key in SUMMARY_KEYS}
    summary['port'] = args.port
    summary['baud'] = args.baud
    summary['seconds'] = args.seconds
    summary['label'] = args.label

    try:
        import serial
    except ImportError:
        print('pyserial not installed: pip install pyserial', file=sys.stderr)
        return 2, summary
    try:
        port = serial.Serial(args.port, args.baud, timeout=0.05)
    except Exception as exc:
        print(f'cannot open {args.port}: {exc}', file=sys.stderr)
        return 2, summary

    log = UartLog()
    winsound_module = None
    frames_received = 0
    crc_errors = 0
    retries = 0
    frame_cnt = None
    t_c = None
    t_d = None
    payloads = []
    rc = 1
    try:
        print(f'UART {args.port} @ {args.baud} open; waiting for boot tokens '
              f'({" / ".join(BOOT_TOKENS)})')
        if args.skip_boot:
            ok, lines, missing = True, [], []
        else:
            ok, lines, missing = wait_for_tokens(port, BOOT_TOKENS, args.boot_timeout, log)
        for line in lines:
            print(f'  boot: {line}')
        if not ok:
            missing = [t for t in BOOT_TOKENS
                       if not any(t in ln for ln in lines)]
            print('boot: FAIL (missing ' + ', '.join(missing) + ')')
            return 5, summary

        if args.play_wav:
            wav_path = Path(args.play_wav)
            if not wav_path.is_file():
                print(f'play wav not found: {wav_path}', file=sys.stderr)
                return 2, summary
            summary['play_wav'] = wav_path.name
            winsound_module = start_playback(wav_path, args.play_device)
            if winsound_module is None:
                print(f'waveOut unavailable: play {wav_path} manually NOW '
                      f'(looping), capture starts in {args.lead} s')
            else:
                print(f'playing {wav_path.name} in a loop on waveOut device {args.play_device}')
        else:
            summary['play_wav'] = None

        if args.no_capture:
            frame_cnt = expected_frames(args.seconds)
            done_line = 'CAPDONE (assumed, --no-capture)'
            t_d = datetime.now().isoformat(timespec='milliseconds')
            print(f'export-only: assuming {frame_cnt} frames already in DDR')
        else:
            time.sleep(args.lead)
            t_c = datetime.now().isoformat(timespec='milliseconds')
            port.write(b'C')
            port.flush()
            print(f"'C' sent at {t_c}; waiting for CAPDONE "
                  f"(budget {args.seconds + 10.0:.0f} s)")

            frame_cnt, done_line = wait_for_capdone(
                port, args.seconds + 10.0, log)
            if frame_cnt is None:
                print('CAPDONE not seen within the capture window')
                return 5, summary
            t_d = datetime.now().isoformat(timespec='milliseconds')
            print(f'CAPDONE: {done_line} at {t_d} -> {frame_cnt} frames '
                  f'({frame_cnt * MAX_PAYLOAD} bytes)')

        reader = FrameReader(port, log)
        for seq in range(frame_cnt):
            payload, bad = fetch_frame(port, reader, seq, args.frame_timeout)
            if bad:
                crc_errors += 1
            if payload is None:
                # One retry per frame (bad CRC or timeout), then fatal.
                retries += 1
                print(f'  frame {seq}: retrying after '
                      f'{"CRC error" if bad else "timeout"}')
                payload, bad = fetch_frame(port, reader, seq, args.frame_timeout)
                if bad:
                    crc_errors += 1
                if payload is None:
                    print(f'frame {seq}: second attempt failed '
                          f'({"CRC error" if bad else "timeout"}); aborting')
                    return 1, summary
            port.write(b'K')
            port.flush()
            payloads.append(payload)
            frames_received += 1
            if (frames_received % 64 == 0 or frames_received == frame_cnt):
                print(f'  {frames_received}/{frame_cnt} frames')
    finally:
        stop_playback(winsound_module)
        port.close()

    pcm = reassemble(payloads)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = OUT_ROOT / f'{args.label}_{stamp}'
    out_dir.mkdir(parents=True, exist_ok=True)
    pcm_path = out_dir / 'pcm.raw'
    wav_path = out_dir / 'capture.wav'
    uart_path = out_dir / 'uart_raw.bin'
    pcm_path.write_bytes(pcm)
    write_wav(wav_path, pcm)
    uart_path.write_bytes(log.raw)
    uart_sha = sha256_file(uart_path)

    summary['frame_cnt'] = frame_cnt
    summary['frames_received'] = frames_received
    summary['crc_errors'] = crc_errors
    summary['retries'] = retries
    summary['pcm_bytes'] = len(pcm)
    summary['uart_sha256'] = uart_sha
    ok = (frame_cnt is not None and frame_cnt > 0
          and frames_received == frame_cnt and crc_errors == 0)
    summary['verdict'] = 'PASS' if ok else 'FAIL'
    rc = 0 if ok else 1

    manifest = {
        'label': args.label,
        'timestamp': stamp,
        'port': args.port,
        'baud': args.baud,
        'seconds': args.seconds,
        'lead': args.lead,
        'expected_frames': expected_frames(args.seconds),
        'play_wav': str(args.play_wav) if args.play_wav else None,
        'play_mode': ('winsound_loop' if args.play_wav and winsound_module
                      else ('manual' if args.play_wav else 'none')),
        'source_wav_sha256': (sha256_file(args.play_wav)
                              if args.play_wav and Path(args.play_wav).is_file()
                              else None),
        'frame_cnt': frame_cnt,
        'frames_received': frames_received,
        'crc_errors': crc_errors,
        'retries': retries,
        'pcm_bytes': len(pcm),
        'sample_rate': SAMPLE_RATE,
        'channels': CHANNELS,
        'pcm_raw': pcm_path.name,
        'capture_wav': wav_path.name,
        'uart_log': uart_path.name,
        'uart_sha256': uart_sha,
        't_c': t_c,
        't_d': t_d,
        'duration_s': len(pcm) / BYTES_PER_SECOND,
        'verdict': summary['verdict'],
    }
    write_manifest(out_dir / 'manifest.json', manifest)

    print(f'pcm: {pcm_path} ({len(pcm)} bytes)')
    print(f'wav: {wav_path} ({SAMPLE_RATE} Hz stereo 16-bit, '
          f'{manifest["duration_s"]:.3f} s)')
    print(f'manifest: {out_dir / "manifest.json"}')
    print(json.dumps({k: summary[k] for k in SUMMARY_KEYS}, indent=2))
    return rc, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--seconds', type=float, default=4.0,
                    help='expected capture window in seconds (CAPDONE '
                         'budget = seconds + 10)')
    ap.add_argument('--lead', type=float, default=1.0,
                    help='seconds between playback start and the C command')
    ap.add_argument('--play-device', type=int, default=PLAY_DEVICE,
                    help='waveOut render device index (default 4 = Realtek)')
    ap.add_argument('--play-wav', default=None,
                    help='wav to loop during the capture (winsound async); '
                         'falls back to a manual-playback prompt')
    ap.add_argument('--label', default=None,
                    help='output label (default: play-wav file stem)')
    ap.add_argument('--boot-timeout', type=float, default=30.0)
    ap.add_argument('--no-capture', action='store_true',
                    help='DDR already holds a finished capture; only export frames')
    ap.add_argument('--skip-boot', action='store_true',
                    help='board is already past I2SCAP BOOT/DDR OK; send C directly')
    ap.add_argument('--frame-timeout', type=float, default=2.0)
    args = ap.parse_args()
    if args.label is None:
        if args.play_wav:
            args.label = Path(args.play_wav).stem
        else:
            args.label = 'capture'
    rc, _ = run_capture(args)
    return rc


if __name__ == '__main__':
    sys.exit(main())
