"""Behavioural DDR3 memory model with the command-address scaling.

The Pango DDR3 IP places a burst at ``physical = ADDR_UNIT * cmd_addr`` and
advances 32 B physically per beat (see scripts/ddr3_layout.py and
docs/DDR3_CONTRACT_20261111.md).  After the ddr3_ctrl_axi >>2 fix the
production default is byte semantics (ADDR_UNIT = 1); the legacy x4 bitstream
is still reproducible by constructing ``Ddr3PhysicalMemory(addr_unit=4)``.

The producers/consumers below are 1:1 transcriptions of the RTL command
geometry, so a test can diff two production paths byte for byte:

  audio_sink   one len=0 write per 32 B page, cmd stride 32
  mel_engine   516 x len=15 reads, cmd stride 512, 16 samples per beat
  weight_loader 256 B frames, one len=7 write per frame, cmd stride 256
  wdma          len=15 reads, cmd addr advances 32 B per beat
  feat export   one len=0 write per 32 B page of 16 x 16-bit slots
  diag_readback 8-beat frames, cmd stride 256
"""

from ddr3_layout import (BEAT_BYTES, FEAT_SLOT_BYTES, FRAME_BYTES,
                         PAGE_BYTES, PROD_ADDR_UNIT, destride, frame_plan)

# Production geometry.
PCM_PAGES = 8256                 # 264,192 B = 132,096 mono int16 per window
MEL_BEATS = 16                   # len=15
MEL_CMD_STRIDE = 512             # 16 beats * 32 B
MEL_COMMANDS = PCM_PAGES * PAGE_BYTES // MEL_CMD_STRIDE   # 516
SAMPLES_PER_BEAT = BEAT_BYTES // 2
WEIGHT_FRAME_BYTES = 256
FEAT_ELEMENTS = 64 * 258         # 16,512 uint8


class Ddr3PhysicalMemory:
    """Flat physical byte array addressed through the command-address unit."""

    def __init__(self, addr_unit=PROD_ADDR_UNIT, size=1 << 24, fill=0xA5):
        self.addr_unit = addr_unit
        self.fill = fill
        self.mem = bytearray([fill]) * size

    def _base(self, cmd_addr):
        return self.addr_unit * cmd_addr

    def write_burst(self, cmd_addr, beats):
        start = self._base(cmd_addr)
        for j, beat in enumerate(beats):
            if len(beat) != BEAT_BYTES:
                raise ValueError("beat %d length %d" % (j, len(beat)))
            off = start + BEAT_BYTES * j
            self.mem[off:off + BEAT_BYTES] = beat

    def read_burst(self, cmd_addr, nbeats):
        start = self._base(cmd_addr)
        return [bytes(self.mem[start + BEAT_BYTES * j:
                              start + BEAT_BYTES * j + BEAT_BYTES])
                for j in range(nbeats)]

    def read_frame(self, cmd_addr):
        """diag_readback: one 8-beat command returns 256 contiguous bytes."""
        return b"".join(self.read_burst(cmd_addr, FRAME_BYTES // BEAT_BYTES))


# --------------------------------------------------------------------------- #
# Production path transcriptions
# --------------------------------------------------------------------------- #

def write_pages(mem, base, pages):
    """audio_sink / feat export: one single-beat write per page."""
    for page, payload in enumerate(pages):
        mem.write_burst(base + PAGE_BYTES * page, [payload])


def read_pages_via_diag(mem, base, npages):
    """Host diag readback: frame plan + destride (the official conversion)."""
    plan = frame_plan(base, npages, mem.addr_unit)
    frames = [mem.read_frame(cmd) for cmd, _spans in plan]
    return destride(frames, plan)


def mel_read_samples(mem, base, ncommands=MEL_COMMANDS):
    """mel_engine PCM read: 16-beat bursts, cmd stride 512, int16 LE."""
    out = []
    for k in range(ncommands):
        for beat in mem.read_burst(base + MEL_CMD_STRIDE * k, MEL_BEATS):
            for s in range(0, BEAT_BYTES, 2):
                out.append(int.from_bytes(beat[s:s + 2], "little", signed=True))
    return out


def upload_frames(mem, base, image):
    """weight_loader: 256 B image frames, one 8-beat write per frame."""
    if len(image) % WEIGHT_FRAME_BYTES:
        raise ValueError("weight image must be a whole number of frames")
    for k in range(len(image) // WEIGHT_FRAME_BYTES):
        chunk = image[k * WEIGHT_FRAME_BYTES:(k + 1) * WEIGHT_FRAME_BYTES]
        mem.write_burst(base + WEIGHT_FRAME_BYTES * k,
                        [chunk[BEAT_BYTES * j:BEAT_BYTES * (j + 1)]
                         for j in range(FRAME_BYTES // BEAT_BYTES)])


def read_contiguous(mem, base, nbytes, beats=MEL_BEATS):
    """wdma: len=15 bursts, cmd addr advances 32 B per beat."""
    out = bytearray()
    addr = base
    while len(out) < nbytes:
        for beat in mem.read_burst(addr, beats):
            out.extend(beat)
        addr += BEAT_BYTES * beats
    return bytes(out[:nbytes])


def feat_slots(elements):
    """Pack feat bytes into {8'h00, feat_data} 16-bit DDR slots.

    feat_data is the low byte of each 16-bit slot; the diag read-back expands
    each beat little-endian (bits 7:0 first), so the byte stream is
    feat_data, 0x00, feat_data, 0x00, ...
    """
    raw = bytearray()
    for value in elements:
        raw.extend(bytes((value, 0)))
    return bytes(raw)


def unpack_feat(raw):
    return bytes(raw[0::FEAT_SLOT_BYTES])
