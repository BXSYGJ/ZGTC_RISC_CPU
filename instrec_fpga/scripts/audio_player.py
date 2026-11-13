#!/usr/bin/env python3
"""Low-latency streaming playback for the board bring-up rigs.

Why this exists
---------------
The rigs used to hand one giant buffer to waveOut (or even a mono buffer the
Realtek endpoint rejects).  Two consequences followed: real-time behaviour was
poor (a whole clip queued at once, so volume/content changes needed a restart
and dropouts were invisible) and there was no volume control, so the PCM1808
either clipped or ran so quiet that its noise floor dominated the mel features.

This module streams in small buffers, keeps N queued, and refills finished ones
from a background thread.  Volume is a digital gain in dBFS plus a full-volume
waveOut handle, and underruns are counted so a bad run is visible instead of
silently producing garbage.

Verify the rendered signal end-to-end by reading the PCM window the FPGA
actually captured (board_accuracy.py does this); that is the ground truth for
"what reached the board".

Usage
-----
    from audio_player import StreamingPlayer
    p = StreamingPlayer(pcm, sr=48000, device_hint='Realtek', gain_db=-6.0)
    p.start(); ...
    print(p.stats())        # {'underruns': 0, 'buffers': 57, 'gain_db': -6.0}
    p.stop()
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time

import numpy as np

WHDR_DONE = 0x00000001


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


class MMDeviceCaps(ctypes.Structure):
    _fields_ = [('wMid', wt.WORD), ('wPid', wt.WORD),
                ('vDriverVersion', wt.UINT), ('szPname', wt.WCHAR * 32),
                ('dwFormats', wt.DWORD), ('wChannels', wt.WORD),
                ('wReserved1', wt.WORD), ('dwSupport', wt.DWORD)]


def list_render_devices(hint=None):
    """Return [(index, name)] for waveOut render endpoints (optionally filtered)."""
    winmm = ctypes.WinDLL('winmm')
    winmm.waveOutGetNumDevs.restype = wt.UINT
    out = []
    for idx in range(winmm.waveOutGetNumDevs()):
        caps = MMDeviceCaps()
        if winmm.waveOutGetDevCapsW(idx, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            if hint is None or hint.lower() in caps.szPname.lower():
                out.append((idx, caps.szPname))
    return out


def resolve_device(hint='Realtek'):
    """waveOut index whose endpoint name contains hint.

    The waveOut index is dynamic (Realtek was 4 on 2026-11-06 and 0 on
    2026-11-13), so it must always be resolved by name, never hard-coded.
    """
    found = list_render_devices(hint)
    if found:
        return found[0][0]
    raise RuntimeError('no render endpoint matching %r; have %s'
                       % (hint, [n for _, n in list_render_devices()]))


class StreamingPlayer:
    """Queue-based waveOut player with digital gain and underrun accounting."""

    def __init__(self, pcm, sr=48000, channels=2, device_hint='Realtek',
                 gain_db=0.0, buf_ms=80, queued=4, max_seconds=None):
        pcm = np.asarray(pcm)
        if pcm.ndim == 1:
            pcm = np.repeat(pcm, channels)
        if pcm.dtype != np.int16:
            pcm = pcm.astype(np.int16)
        self.pcm = pcm
        self.sr = int(sr)
        self.channels = int(channels)
        self.buf_frames = max(1, int(self.sr * buf_ms / 1000.0))
        self.queued = max(2, int(queued))
        self.gain = float(10.0 ** (float(gain_db) / 20.0))
        self.gain_db = float(gain_db)
        self.device_id = resolve_device(device_hint)
        self._winmm = ctypes.WinDLL('winmm')
        self._handle = wt.HANDLE()
        self._hdrs = []
        self._bufs = []
        self._pos = 0
        self._stop = threading.Event()
        self._thread = None
        self.underruns = 0
        self.buffers = 0
        self.started = False
        self.total_frames = None if max_seconds is None else int(max_seconds * self.sr)

    def start(self):
        wfmt = WAVEFORMATEX(1, self.channels, self.sr,
                            self.sr * self.channels * 2,
                            self.channels * 2, 16, 0)
        rc = self._winmm.waveOutOpen(ctypes.byref(self._handle), self.device_id,
                                     ctypes.byref(wfmt), 0, 0, 0)
        if rc != 0:
            raise RuntimeError('waveOutOpen(dev=%d) rc=%d (mono or unsupported format?)'
                               % (self.device_id, rc))
        try:
            self._winmm.waveOutSetVolume.argtypes = [wt.HANDLE, wt.DWORD]
            self._winmm.waveOutSetVolume.restype = wt.UINT
            self._winmm.waveOutSetVolume(self._handle, 0xFFFFFFFF)
        except Exception:
            pass
        self._hdrs = [WAVEHDR(None, 0, 0, None, 0, 0, None, None)
                      for _ in range(self.queued)]
        self._bufs = [None] * self.queued
        self.started = True
        self._stop.clear()
        for i in range(self.queued):
            self._fill(i)
        self._thread = threading.Thread(target=self._refill_loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if not self.started:
            return
        try:
            self._winmm.waveOutReset(self._handle)
            for i in range(self.queued):
                if self._bufs[i] is not None:
                    self._winmm.waveOutUnprepareHeader(
                        self._handle, ctypes.byref(self._hdrs[i]),
                        ctypes.sizeof(WAVEHDR))
            self._winmm.waveOutClose(self._handle)
        finally:
            self.started = False

    def _next_chunk(self):
        n = self.buf_frames * self.channels
        out = np.empty(n, dtype=np.int16)
        filled = 0
        while filled < n:
            if (self.total_frames is not None
                    and self._pos >= self.total_frames * self.channels):
                return None
            take = min(n - filled, self.pcm.size - self._pos)
            out[filled:filled + take] = self.pcm[self._pos:self._pos + take]
            self._pos += take
            if self._pos >= self.pcm.size:
                self._pos = 0
            filled += take
        if self.gain != 1.0:
            out = np.clip(out.astype(np.float32) * self.gain, -32768, 32767).astype(np.int16)
        return out

    def _fill(self, i):
        chunk = self._next_chunk()
        if chunk is None:
            return False
        buf = chunk.tobytes()
        hdr = self._hdrs[i]
        hdr.dwBufferLength = len(buf)
        hdr.dwFlags = 0
        hdr.lpData = buf
        self._bufs[i] = buf
        self._winmm.waveOutPrepareHeader(self._handle, ctypes.byref(hdr),
                                         ctypes.sizeof(WAVEHDR))
        self._winmm.waveOutWrite(self._handle, ctypes.byref(hdr),
                                 ctypes.sizeof(WAVEHDR))
        self.buffers += 1
        return True

    def _refill_loop(self):
        while not self._stop.is_set():
            progressed = False
            for i in range(self.queued):
                hdr = self._hdrs[i]
                if hdr.dwFlags & WHDR_DONE:
                    self._winmm.waveOutUnprepareHeader(
                        self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
                    if self._fill(i):
                        progressed = True
                    else:
                        self.underruns += 1
            if not progressed:
                time.sleep(0.005)

    def stats(self):
        return {'underruns': self.underruns, 'buffers': self.buffers,
                'gain_db': self.gain_db, 'device_id': self.device_id,
                'buf_ms': 1000.0 * self.buf_frames / self.sr,
                'queued': self.queued}


def write_wav(path, pcm, sr=48000, channels=2):
    """Write int16 PCM (mono input duplicated to channels)."""
    import wave
    a = np.asarray(pcm)
    if a.ndim == 1 and channels >= 2:
        a = np.repeat(a, channels)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(a.astype('<i2').tobytes())


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='stream a wav to a render endpoint')
    ap.add_argument('wav', nargs='?')
    ap.add_argument('--device-hint', default='Realtek')
    ap.add_argument('--gain-db', type=float, default=0.0)
    ap.add_argument('--seconds', type=float, default=5.0)
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    if a.list or not a.wav:
        for i, n in list_render_devices():
            print(i, n)
        raise SystemExit(0)
    import wave
    with wave.open(a.wav, 'rb') as w:
        sr, ch = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), '<i2')
    if ch == 1:
        pcm = np.repeat(pcm, 2)
        ch = 2
    p = StreamingPlayer(pcm, sr=sr, channels=ch, device_hint=a.device_hint,
                        gain_db=a.gain_db).start()
    time.sleep(a.seconds)
    print(p.stats())
    p.stop()
