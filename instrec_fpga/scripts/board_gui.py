#!/usr/bin/env python3
"""InstRec board GUI: play a clip, watch the Mel spectrum and the classifier.

What it does
------------
* lists audio clips from a directory (default: the model's own 8-class demo set,
  one clip per class, so the displayed class actually means something),
* plays the selected clip through a chosen render endpoint while **managing the
  volume automatically** -- unmute, pin the endpoint slider, peak-normalise every
  clip to the same level, and show the board's measured PCM level so a dead
  analogue link is visible instead of silent,
* polls the board over the diag UART and draws
  - the exported Mel dB spectrum (DDR3 0x0020_0000, 64 x 258, Q8.8 dB), and
  - the 8 logits from the 'G' command, with softmax confidence and the label.

Threading
---------
Tkinter must be driven from one thread, and the diag UART is not re-entrant, so
all board I/O happens in a single worker thread fed by a queue; results come
back through ``after()``.

Usage
-----
    python scripts/board_gui.py
    python scripts/board_gui.py --port COM5 --device-hint NICEHCK
    python scripts/board_gui.py --clips D:/0000/111/001/Pango/InstRec/data/demo
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import tkinter as tk
from tkinter import filedialog, ttk

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import board_accuracy as ba                      # noqa: E402

DEFAULT_CLIPS = Path("D:/0000/111/001/Pango/InstRec/data/demo")
WINDOW_SAMPLES = 132096          # 2.752 s @ 48 kHz, 258 x 512 hop
SPEC_BASE = 0x00200000
SPEC_WORDS = 64 * 258
SPEC_BYTES = SPEC_WORDS * 2


def softmax(x):
    x = np.asarray(x, dtype=np.float64)
    e = np.exp(x - x.max())
    return e / e.sum()


class BoardApp(tk.Tk):
    def __init__(self, port: str, device_hint: str, clips: Path):
        super().__init__()
        self.title("InstRec-FPGA 板级演示")
        self.geometry("1180x720")

        self.port = port
        self.device_hint = device_hint
        self.clip_dir = clips
        self.clips: list[Path] = []
        self.ser = None
        self.player = None
        self.spec = None
        self.logits = None
        self.last_pcm_std = None
        self.last_win = None

        self.tasks: queue.Queue = queue.Queue()
        self.playing = False

        self._build_ui()
        self._reload_clips()
        self._start_worker()
        self.after(500, self._tick)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        import matplotlib
        matplotlib.use("TkAgg")
        matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei",
                                                  "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer, width=320)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        ttk.Label(left, text="片段").pack(anchor="w")
        self.listbox = tk.Listbox(left, height=18, exportselection=False)
        self.listbox.pack(fill="both", expand=True, pady=4)

        row = ttk.Frame(left)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="播放", command=self.play_selected).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="停止", command=self.stop_playback).pack(side="left", expand=True, fill="x")

        row2 = ttk.Frame(left)
        row2.pack(fill="x", pady=2)
        ttk.Button(row2, text="读 logits", command=lambda: self._submit("logits")).pack(side="left", expand=True, fill="x")
        ttk.Button(row2, text="抓 Mel 频谱", command=lambda: self._submit("spec")).pack(side="left", expand=True, fill="x")

        row3 = ttk.Frame(left)
        row3.pack(fill="x", pady=2)
        ttk.Button(row3, text="选择目录…", command=self._pick_dir).pack(side="left", expand=True, fill="x")
        ttk.Button(row3, text="重连串口", command=self._reconnect).pack(side="left", expand=True, fill="x")

        box = ttk.LabelFrame(left, text="音量（自动管理）", padding=6)
        box.pack(fill="x", pady=6)
        self.vol_var = tk.IntVar(value=50)
        self.vol_label = ttk.Label(box, text="端点音量 50%")
        self.vol_scale = ttk.Scale(box, from_=0, to=100, orient="horizontal",
                                   command=self._on_volume)
        self.vol_scale.set(50)
        self.vol_scale.pack(fill="x")
        self.vol_label.pack(anchor="w")
        self.norm_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="峰值归一化（统一电平）", variable=self.norm_var).pack(anchor="w")
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="播放前解除静音", variable=self.auto_var).pack(anchor="w")

        self.level_label = ttk.Label(left, text="板级电平：—", foreground="#666")
        self.level_label.pack(anchor="w", pady=4)
        self.status = ttk.Label(left, text="未连接", wraplength=300, justify="left")
        self.status.pack(anchor="w", pady=4)

        right = ttk.Frame(outer)
        right.pack(side="left", fill="both", expand=True)
        self.fig = Figure(figsize=(7.6, 6.6), dpi=100)
        self.ax_spec = self.fig.add_subplot(211)
        self.ax_logit = self.fig.add_subplot(212)
        self._draw_idle_axes()
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _draw_idle_axes(self):
        self.ax_spec.set_title("Mel dB 频谱（板级导出 0x00200000）")
        self.ax_spec.set_xlabel("帧")
        self.ax_spec.set_ylabel("Mel bin")
        self.ax_spec.text(0.5, 0.5, "点「抓 Mel 频谱」读取", ha="center", va="center",
                          transform=self.ax_spec.transAxes, color="#999")
        self.ax_logit.set_title("分类 logits")
        self.ax_logit.set_xticks(range(8))
        self.ax_logit.set_xticklabels([n[:9] for n in ba.CLASS_NAMES], rotation=25, fontsize=8)
        self.fig.tight_layout()

    # ------------------------------------------------------------ helpers
    def _reload_clips(self):
        self.clips = sorted(self.clip_dir.glob("*.wav"))
        self.listbox.delete(0, "end")
        for c in self.clips:
            self.listbox.insert("end", c.name)
        if self.clips:
            self.listbox.selection_set(0)
        self._set_status("片段目录：%s（%d 条）" % (self.clip_dir, len(self.clips)))

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=str(self.clip_dir))
        if d:
            self.clip_dir = Path(d)
            self._reload_clips()

    def _set_status(self, text):
        self.status.config(text=text)

    def _on_volume(self, _evt=None):
        v = int(float(self.vol_scale.get()))
        self.vol_var.set(v)
        if hasattr(self, "vol_label"):
            self.vol_label.config(text="端点音量 %d%%" % v)
        self._submit("volume", v)

    def _reconnect(self):
        self._submit("connect")

    # ------------------------------------------------------------- worker
    def _start_worker(self):
        self._submit("connect")
        t = threading.Thread(target=self._worker_loop, daemon=True)
        t.start()

    def _submit(self, kind, *args):
        self.tasks.put((kind, args))

    def _worker_loop(self):
        while True:
            kind, args = self.tasks.get()
            try:
                if kind == "connect":
                    self._do_connect()
                elif kind == "volume":
                    self._do_volume(args[0])
                elif kind == "logits":
                    self._do_logits()
                elif kind == "spec":
                    self._do_spec()
                elif kind == "level":
                    self._do_level()
            except Exception:
                msg = traceback.format_exc(limit=3)
                self.after(0, self._set_status, "操作失败：\n" + msg[-400:])

    def _ensure_serial(self):
        import serial
        if self.ser is not None:
            return self.ser
        self.ser = serial.Serial(self.port, 115200, timeout=2.0)
        time.sleep(0.2)
        self.ser.reset_input_buffer()
        self.ser.write(b"U")          # never inherit a stale lock
        time.sleep(0.05)
        return self.ser

    def _do_connect(self):
        try:
            self._ensure_serial()
            import diag_dump as dd
            st = dd.read_status(self.ser)
            self.after(0, self._set_status,
                       "已连接 %s  win=%d" % (self.port, st.get("win", -1)))
        except Exception as exc:
            self.ser = None
            self.after(0, self._set_status, "串口未连接：%s" % str(exc)[:120])

    def _do_volume(self, v):
        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except Exception:
            return
        for d in AudioUtilities.GetAllDevices():
            name = str(d.FriendlyName)
            if self.device_hint.lower() not in name.lower() or name.startswith("麦克风"):
                continue
            try:
                vol = d._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None
                                      ).QueryInterface(IAudioEndpointVolume)
            except Exception:
                continue
            vol.SetMute(0, None)
            vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, v / 100.0)), None)

    def _do_logits(self):
        import diag_dump as dd
        ser = self._ensure_serial()
        st = dd.read_status(ser)
        lg = dd.read_logits(ser)
        self.after(0, self._on_logits, st, lg)

    def _do_level(self):
        import diag_dump as dd
        ser = self._ensure_serial()
        std = ba.board_pcm_std(ser, dd)
        self.after(0, self._on_level, std)

    def _do_spec(self):
        import diag_spectrum as ds
        ser = self._ensure_serial()
        raw = ds.read_ddr_robust(ser, SPEC_BASE, SPEC_BYTES)
        db = np.frombuffer(raw, dtype="<i2").astype(np.int32).reshape(258, 64).T
        self.after(0, self._on_spec, db)

    # ------------------------------------------------------------ results
    def _on_level(self, std):
        self.last_pcm_std = std
        if std < 50:
            txt, col = "板级电平：%.0f  ⚠ 无信号（端点静音/接线）" % std, "#c00"
        elif std < 300:
            txt, col = "板级电平：%.0f  ⚠ 偏低" % std, "#c60"
        else:
            txt, col = "板级电平：%.0f  ✓" % std, "#070"
        self.level_label.config(text=txt, foreground=col)

    def _on_logits(self, st, lg):
        self.logits = np.asarray(lg)
        self.last_win = st.get("win")
        p = softmax(self.logits)
        top = int(np.argmax(self.logits))
        self.ax_logit.clear()
        self.ax_logit.set_title("分类 logits   →  %s  (%.1f%%)   win=%s"
                                % (ba.CLASS_NAMES[top], 100.0 * p[top], self.last_win))
        colors = ["#c9c9c9"] * 8
        colors[top] = "#1f77b4"
        self.ax_logit.bar(range(8), self.logits, color=colors)
        self.ax_logit.set_xticks(range(8))
        self.ax_logit.set_xticklabels([n[:9] for n in ba.CLASS_NAMES], rotation=25, fontsize=8)
        self.ax_logit.axhline(0, color="#888", linewidth=0.6)
        self.fig.tight_layout()
        self.canvas.draw_idle()
        self._set_status("logits=%s\n置信度 %.1f%%  (%s)"
                         % (list(map(int, self.logits)), 100.0 * p[top], ba.CLASS_NAMES[top]))

    def _on_spec(self, db):
        self.spec = db
        live = db[db > -20480]
        vmax = float(live.max()) if live.size else -256.0
        vmin = vmax - 80 * 256
        self.ax_spec.clear()
        self.ax_spec.set_title("Mel dB 频谱（板级导出 0x00200000）  "
                               "min %.0f / max %.0f dB" % (db.min() / 256.0, db.max() / 256.0))
        im = self.ax_spec.imshow(db, aspect="auto", origin="lower",
                                 vmin=vmin, vmax=vmax, cmap="magma")
        self.ax_spec.set_xlabel("帧")
        self.ax_spec.set_ylabel("Mel bin")
        if not hasattr(self, "_cbar"):
            self._cbar = self.fig.colorbar(im, ax=self.ax_spec, pad=0.01)
        else:
            self._cbar.update_normal(im)
        self.fig.tight_layout()
        self.canvas.draw_idle()
        self._set_status("频谱已读取：%d 帧 × 64 bin" % db.shape[1])

    # ---------------------------------------------------------- playback
    def play_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        clip = self.clips[sel[0]]
        try:
            from audio_player import StreamingPlayer
            pcm48 = ba.prep_clip(clip, -1.0)
        except Exception:
            from scipy.io import wavfile
            sr, x = wavfile.read(clip)
            x = np.asarray(x, dtype=np.float64)
            m = max(abs(float(x.max())), abs(float(x.min())), 1e-9)
            x = np.clip(x / m, -1.0, 1.0) * 32767.0
            x = np.round(x).astype(np.int16)
            if x.ndim == 2:
                x = x[:, 0]
            pcm48 = ba.resample_to_48k(x, sr)
            if self.norm_var.get():
                peak = float(np.abs(pcm48).max()) or 1.0
                pcm48 = np.clip(pcm48 * (32767.0 * 0.89 / peak), -32768, 32767).astype(np.int16)

        unit = np.tile(pcm48, int(np.ceil(WINDOW_SAMPLES / max(1, pcm48.size))))
        unit = unit[:WINDOW_SAMPLES]
        pcm = ba.loop_to(unit, 60)

        self.stop_playback()
        if self.auto_var.get():
            self._submit("volume", int(self.vol_var.get()))
        try:
            self.player = StreamingPlayer(pcm, sr=48000, channels=2,
                                          device_hint=self.device_hint, gain_db=0.0,
                                          buf_ms=60, queued=4).start()
        except Exception as exc:
            self._set_status("播放失败：%s" % str(exc)[:150])
            return
        self.playing = True
        truth = None
        stem = clip.stem
        if stem.startswith("sample_"):
            try:
                truth = int(stem.split("_")[1])
            except Exception:
                truth = None
        self._set_status("播放中：%s%s" % (clip.name,
                                          "（真值 %s）" % ba.CLASS_NAMES[truth] if truth is not None else ""))

    def stop_playback(self):
        if self.player is not None:
            try:
                self.player.stop()
            except Exception:
                pass
            self.player = None
        self.playing = False

    # -------------------------------------------------------------- tick
    def _tick(self):
        if self.playing:
            self._submit("level")
        self.after(2000, self._tick)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--device-hint", default="NICEHCK")
    ap.add_argument("--clips", default=str(DEFAULT_CLIPS))
    args = ap.parse_args(argv)
    app = BoardApp(args.port, args.device_hint, Path(args.clips))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
