import ctypes, ctypes.wintypes as wt, sys, time, wave

winmm = ctypes.WinDLL('winmm')
class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [('wFormatTag', wt.WORD), ('nChannels', wt.WORD),
                ('nSamplesPerSec', wt.DWORD), ('nAvgBytesPerSec', wt.DWORD),
                ('nBlockAlign', wt.WORD), ('wBitsPerSample', wt.WORD), ('cbSize', wt.WORD)]
class WAVEHDR(ctypes.Structure):
    _fields_ = [('lpData', ctypes.c_char_p), ('dwBufferLength', wt.DWORD),
                ('dwBytesRecorded', wt.DWORD), ('dwUser', ctypes.c_void_p),
                ('dwFlags', wt.DWORD), ('dwLoops', wt.DWORD),
                ('lpNext', ctypes.c_void_p), ('reserved', ctypes.c_void_p)]

path = sys.argv[1]; dev = int(sys.argv[2]); secs = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
w = wave.open(path, 'rb')
sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
data = w.readframes(w.getnframes()); w.close()
wf = WAVEFORMATEX(1, ch, sr, sr*ch*sw, ch*sw, sw*8, 0)
h = wt.HANDLE()
rc = winmm.waveOutOpen(ctypes.byref(h), dev, ctypes.byref(wf), 0, 0, 0)
print('waveOutOpen dev', dev, 'rc', rc, 'sr', sr, 'ch', ch); sys.stdout.flush()
hdr = WAVEHDR(data, len(data), 0, None, 0, 0, None, None)
winmm.waveOutPrepareHeader(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
winmm.waveOutWrite(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
time.sleep(secs)
winmm.waveOutReset(h); winmm.waveOutClose(h)
print('playback finished')
