#!/usr/bin/env python3
"""Board-level accuracy harness: play labelled clips, read board logits, score.

Pipeline per clip
-----------------
1. load a labelled wav (default: IRMAS val split), resample to 48 kHz,
   loop it to >= --clip-seconds so at least one full 2.752 s window lands;
2. play it on the Realtek endpoint (the one wired to the PCM1808), wait for
   the window to complete, read the 8 int32 logits over the diag 'G' command;
3. top1 = argmax(logits);
4. optionally run the *same* clip through the offline golden pipeline
   (48 kHz mel tables + medley_48k contract/weight image) and compare.

Class ids follow deploy/class_names.json:
  0 clarinet, 1 distorted electric guitar, 2 female singer, 3 flute,
  4 piano, 5 tenor saxophone, 6 trumpet, 7 violin

IRMAS folder codes -> class id:
  cla->0, dis->1, fem->2, flu->3, pia->4, sax->5, tru->6, vio->7
(gel/gac/cel/org/voi are outside the model's 8 classes and are skipped.)

Usage
-----
  python scripts/board_accuracy.py --per-class 3
  python scripts/board_accuracy.py --per-class 5 --classes cla,flu,pia,sax,tru,vio,gel
  python scripts/board_accuracy.py --per-class 3 --json build/acc_board.json
"""
import argparse
import json
import sys
import time
import wave
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

IR = Path('D:/0000/111/001/Pango/InstRec')
CODE_TO_CLASS = {'cla': 0, 'dis': 1, 'fem': 2, 'flu': 3,
                 'pia': 4, 'sax': 5, 'tru': 6, 'vio': 7}
CLASS_NAMES = ['clarinet', 'distorted electric guitar', 'female singer', 'flute',
               'piano', 'tenor saxophone', 'trumpet', 'violin']


def read_wav(path):
    with wave.open(str(path), 'rb') as w:
        ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    a = np.frombuffer(raw, '<i2')
    if ch == 2:
        a = ((a[0::2].astype(np.int32) + a[1::2].astype(np.int32) + 1) >> 1).astype(np.int16)
    return a, sr


def resample_to_48k(pcm, sr):
    if sr == 48000:
        return pcm
    from scipy.signal import resample_poly
    g = np.gcd(sr, 48000)
    return resample_poly(pcm.astype(np.float64), 48000 // g, sr // g)        .round().clip(-32768, 32767).astype(np.int16)


def loop_to(pcm, seconds, sr=48000):
    need = int(seconds * sr)
    if pcm.size == 0:
        return np.zeros(need, np.int16)
    reps = int(np.ceil(need / pcm.size))
    return np.tile(pcm, reps)[:need]


def write_wav(path, pcm, sr=48000):
    """Write 48 kHz STEREO.

    The Realtek endpoint rejects a 1-channel format (waveOutOpen fails and the
    clip is silently never played -- measured 2026-11-13: mono gave PCM std~5
    at the board, i.e. the engine was classifying silence).
    """
    stereo = np.repeat(pcm.astype('<i2'), 2)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())


def pick_clips(per_class, classes):
    """Return [(class_id, path)] picked from the IRMAS val split."""
    fl = json.load(open(IR / 'data/irmas_cache/file_list.json'))
    sp = json.load(open(IR / 'data/irmas_cache/split.json'))
    val = set(sp['val_indices'])
    buckets = defaultdict(list)
    for i, p in enumerate(fl):
        if i not in val:
            continue
        code = Path(p).parent.name
        if code in CODE_TO_CLASS:
            buckets[CODE_TO_CLASS[code]].append(Path(p))
    out = []
    for c in classes:
        out.extend((c, p) for p in buckets.get(c, [])[:per_class])
    return out


def board_pcm_std(ser, dd, nbytes=8192):
    """Peak-hold std of the two PCM ping-pong halves on the board.

    This is the ground truth for "did the clip actually reach the FPGA":
    endpoint mute, a rejected wave format or a dead cable all show up as a
    near-zero std here long before they can be mistaken for a model error.
    """
    vals = []
    for base in (dd.PCM_LASE, dd.PCM_LASE + dd.PCM_WIN_STRIDE):
        try:
            b = dd.read_ddr(ser, base, nbytes)
            vals.append(float(np.frombuffer(b, '<i2').std()))
        except Exception:
            pass
    return max(vals) if vals else 0.0


def offline_top1(pcm48, tables, contract, weights, window):
    """Golden top1 on exactly the PCM the board is played (48 kHz, normalized)."""
    from golden_pipeline import run_mel_pipeline, npu_forward
    pcm = np.tile(pcm48, int(np.ceil(window / max(1, pcm48.size))))[:window]
    # run_mel_pipeline() defaults to the legacy 44.1 kHz contract in
    # scripts/outputs/layer_contract.json (zp_in=49, inv_s_in=267723430).
    # The 48 kHz build quantizes with zp_in=47 / inv_s_in=236403274, so the
    # scale MUST come from the same contract the NPU runs with, otherwise the
    # offline label is computed from a 13 % over-scaled feature and every
    # board-vs-offline comparison is meaningless.
    rec = contract.get('quant_stub_input_contract', contract)
    feat = run_mel_pipeline(pcm, tables,
                            inv_s_in=int(rec['inv_s_in']),
                            zp_in=int(rec['zp_in']))['feat']
    out = npu_forward(feat, contract, tables['exp_lut'], weights=weights)
    return int(out['top1']), [int(v) for v in out['logits']]


def prep_clip(path, peak_dbfs=-1.0):
    """48 kHz mono, peak-normalised so the analog line-out keeps SNR.

    Without this the IRMAS excerpts arrive at std~270 LSB and the PCM1808
    noise floor dominates the mel features (measured 2026-11-13).
    """
    pcm, sr = read_wav(path)
    pcm = resample_to_48k(pcm, sr).astype(np.float64)
    peak = float(np.abs(pcm).max()) or 1.0
    target = 32767.0 * (10.0 ** (peak_dbfs / 20.0))
    return np.clip(pcm * (target / peak), -32768, 32767).round().astype(np.int16)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--per-class', type=int, default=3)
    ap.add_argument('--classes', default='cla,flu,pia,sax,tru,vio',
                    help='comma separated IRMAS codes (default: the 6 exact classes present)')
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--wait', type=float, default=8.0,
                    help='seconds to play before the first read (window is 2.75 s; '
                         '2-3 windows settle the logits)')
    ap.add_argument('--reads', type=int, default=2,
                    help='logit reads per clip, spaced 3 s, majority wins')
    ap.add_argument('--clip-seconds', type=float, default=13.0)
    ap.add_argument('--peak-dbfs', type=float, default=-1.0,
                    help='playback peak normalisation target (default -1 dBFS)')
    ap.add_argument('--volume-db', type=float, default=0.0,
                    help='extra digital gain on top of the peak normalisation')
    ap.add_argument('--device-hint', default='Realtek')
    ap.add_argument('--settle', type=float, default=6.0,
                    help='max seconds to wait for the board to hold this clip')
    ap.add_argument('--std-min', type=float, default=400.0,
                    help='board PCM std below this marks the clip INVALID')
    ap.add_argument('--image', default='scripts/outputs/medley_48k/weights_image.bin')
    ap.add_argument('--no-offline', action='store_true')
    ap.add_argument('--json', dest='json_path', default=None)
    args = ap.parse_args(argv)

    import serial
    import audio_player as apx
    import diag_dump as dd

    codes = [c.strip() for c in args.classes.split(',') if c.strip()]
    wanted = sorted({CODE_TO_CLASS[c] for c in codes if c in CODE_TO_CLASS})
    clips = pick_clips(args.per_class, wanted)
    if not clips:
        print('no clips selected')
        return 2
    print('clips: %d (%d classes), per_class=%d' % (len(clips), len(wanted), args.per_class))

    tables = contract = weights = None
    window = 132096
    if not args.no_offline:
        import golden_pipeline as gp
        tables = gp.load_mel_tables(ROOT / 'scripts/outputs/mel_tables_48k.json')
        contract = gp.load_layer_contract(ROOT / 'scripts/outputs/medley_48k/layer_contract.json')
        weights = gp.load_weights_from_image(contract, ROOT / args.image)
        window = gp.WINDOW_SAMPLES
        print('offline: sr=%s zp_in=%s' % (tables['params'].get('sr'),
                                           contract['quant_stub_input_contract']['zp_in']))

    tmp = ROOT / 'build' / 'acc_tmp'
    tmp.mkdir(parents=True, exist_ok=True)

    ser = serial.Serial(args.port, 115200, timeout=0.4)
    time.sleep(0.2)
    dev = apx.resolve_device(args.device_hint)
    print('play device = %s (%d)' % (args.device_hint, dev))

    rows = []
    conf = Counter()
    ok = 0
    n_valid = 0
    agree = 0
    t0 = time.time()
    window_len = 132096          # hardware window; looping exactly this many
    for idx, (cls, src) in enumerate(clips, 1):
        pcm48 = prep_clip(IR / src, args.peak_dbfs)
        # Phase-locked loop: repeat a slice of exactly one hardware window so
        # every 2.752 s window the engine sees is identical content.  Without
        # this the window start lands at a random phase of the excerpt and
        # board/offline disagree on the same clip.
        unit = np.tile(pcm48, int(np.ceil(window_len / max(1, pcm48.size))))[:window_len]
        pcm48 = unit
        pcm = loop_to(unit, args.clip_seconds)
        reads = []
        pcm_std = 0.0
        pstats = {}
        # Up to two attempts: the very first open after a previous stop
        # occasionally delivers no audio for the whole settle window.
        for attempt in range(2):
            player = apx.StreamingPlayer(pcm, sr=48000, channels=2,
                                         device_hint=args.device_hint,
                                         gain_db=args.volume_db,
                                         buf_ms=60, queued=4).start()
            reads = []
            pcm_std = 0.0
            try:
                time.sleep(0.3)
                deadline = time.time() + args.settle
                while time.time() < deadline:
                    time.sleep(0.4)
                    pcm_std = board_pcm_std(ser, dd)
                    if pcm_std >= args.std_min:
                        break
                if pcm_std >= args.std_min:
                    time.sleep(args.wait)
                    for k in range(max(1, args.reads)):
                        reads.append(dd.read_logits(ser))
                        if k + 1 < max(1, args.reads):
                            time.sleep(2.5)
            finally:
                pstats = player.stats()
                player.stop()
            if pcm_std >= args.std_min:
                break
            time.sleep(0.8)
        votes = [int(np.argmax(r)) for r in reads]
        got = Counter(votes).most_common(1)[0][0] if votes else 0
        logits = reads[-1] if reads else []
        valid = pcm_std >= args.std_min
        if valid:
            ok += (got == cls)
            conf[(cls, got)] += 1
            n_valid += 1

        ref = None
        if tables is not None:
            try:
                ref = offline_top1(pcm48, tables, contract, weights, window)[0]
                agree += (ref == got)
            except Exception as exc:      # keep the board row even if the ref fails
                print('  offline ref failed: %s' % exc)
        rows.append({'i': idx, 'true': cls, 'true_name': CLASS_NAMES[cls],
                     'board': got, 'board_name': CLASS_NAMES[got],
                     'offline': ref, 'logits': [int(v) for v in logits],
                     'pcm_std': pcm_std, 'valid': valid,
                     'underruns': pstats.get('underruns'),
                     'file': str(src)})
        print('[%2d/%2d] %-9s expect %d(%s) board %d(%s) %s pcm=%5.0f%s%s  logits=%s' % (
            idx, len(clips), src.parent.name,
            cls, CLASS_NAMES[cls][:8], got, CLASS_NAMES[got][:8],
            'OK  ' if got == cls else 'MISS', pcm_std,
            '' if valid else ' INVALID',
            ('  off=%d' % ref) if ref is not None else '',
            [int(v) for v in logits]))
        time.sleep(0.5)

    ser.close()
    n = len(rows)
    acc = 100.0 * ok / max(1, n_valid)
    print('')
    print('BOARD accuracy = %d/%d valid = %.1f%%   (%d invalid, %.0f s)' % (
        ok, n_valid, acc, n - n_valid, time.time() - t0))
    if tables is not None:
        print('board vs offline agreement = %d/%d = %.1f%%' % (agree, n, 100.0 * agree / n))
    print('per-class:')
    for c in wanted:
        cc = [r for r in rows if r['true'] == c]
        if cc:
            k = sum(1 for r in cc if r['board'] == c)
            print('  %d %-24s %d/%d' % (c, CLASS_NAMES[c], k, len(cc)))
    miss = [(r['true'], r['board']) for r in rows if r['true'] != r['board']]
    if miss:
        print('confusion (true->got):', ', '.join('%d->%d x%d' % (a, b, k)
                                                  for (a, b), k in Counter(miss).items()))

    if args.json_path:
        out = Path(args.json_path)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            'clips': n, 'correct': ok, 'accuracy': acc / 100.0,
            'board_vs_offline_agreement': (agree / n) if tables is not None else None,
            'per_class': {str(c): {'n': sum(1 for r in rows if r['true'] == c),
                                   'correct': sum(1 for r in rows if r['true'] == c and r['board'] == c)}
                          for c in wanted},
            'rows': rows,
        }, indent=2), encoding='utf-8')
        print('json:', out)
    return 0 if ok == n else 1


if __name__ == '__main__':
    raise SystemExit(main())
