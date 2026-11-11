"""Single source of truth for the InstRec DDR3 command-address layout.

Contract (see docs/DDR3_CONTRACT_20261111.md section 6):

    physical_byte = ADDR_UNIT * cmd_addr + BEAT_BYTES * beat

The Pango DDR3 IP consumes the 28-bit ``cmd.addr`` that ddr3_ctrl_axi drives on
axi_awaddr / axi_araddr as a 32-bit word index, not as a byte address.  The
controller has now been fixed to drive ``cur_addr >> 2`` on that boundary, so
production traffic is byte semantics (PROD_ADDR_UNIT = 1):

  * one burst of N beats occupies the contiguous physical range
    ``[A, A + 32*N)``;
  * pages sit at physical ``32*page`` and sparse single-beat writes match
    contiguous burst reads.

The pre-fix bitstream (SHA-256 69041235...) had ADDR_UNIT = 4: every 32 B page
landed at physical 128*page, so sparse single-beat writes (audio_sink, feat
export) did NOT match contiguous burst reads (mel, wdma).  Read-back of that
old bitstream must pass LEGACY_X4_ADDR_UNIT explicitly; the default here is the
fixed byte semantics.

A "page" below is the 32 B unit every producer emits (16 x int16 samples or
16 x uint16 feat slots).  Pages sit at cmd address ``base + 32*page`` under
both units; only their physical spacing changes (128 B vs 32 B).

Nothing here touches hardware: every function is pure and unit tested.
"""

PAGE_BYTES = 32
BEAT_BYTES = 32
FRAME_BYTES = 256          # diag_readback frame: 8 beats
BEATS_PER_FRAME = FRAME_BYTES // BEAT_BYTES

# Address units.  After the ddr3_ctrl_axi >>2 fix (2026-11-11) the controller
# drives WORD addresses on the IP boundary, which restores byte semantics end
# to end: production traffic is PROD_ADDR_UNIT = 1.  The pre-fix bitstream had
# the Pango IP consume the command address as a 32-bit word index, i.e.
# LEGACY_X4_ADDR_UNIT = 4; the host read-back must destride that old bitstream.
PROD_ADDR_UNIT = 1         # byte semantics: production after the >>2 fix
BYTE_ADDR_UNIT = 1         # documented byte semantics (== PROD_ADDR_UNIT)
LEGACY_X4_ADDR_UNIT = 4    # pre-fix bitstream: IP treated addr as word index
HW_ADDR_UNIT = LEGACY_X4_ADDR_UNIT   # historical name, now = legacy x4 unit

FEAT_SLOT_BYTES = 2        # feat element occupies a 16-bit DDR slot


def page_addr(base, page, page_bytes=PAGE_BYTES):
    """Command address of page ``page`` inside the region starting at base."""
    return base + page * page_bytes


def physical(addr, addr_unit=PROD_ADDR_UNIT):
    """Physical byte offset of a command address."""
    return addr * addr_unit


def pages_per_frame(addr_unit=PROD_ADDR_UNIT):
    """How many 32 B pages fit in one 256 B diag frame.

    unit=4: 256 physical bytes hold 2 pages; unit=1: 8 pages.
    """
    if FRAME_BYTES % (PAGE_BYTES * addr_unit) != 0:
        raise ValueError("addr_unit %r does not divide the frame" % (addr_unit,))
    return FRAME_BYTES // (PAGE_BYTES * addr_unit)


def frame_plan(base, npages, addr_unit=PROD_ADDR_UNIT):
    """Return ``[(cmd_addr, [(payload_offset, nbytes), ...]), ...]``.

    Each diag ``R`` of len=256 returns one 256 B frame; the spans select the
    bytes that belong to real pages.  Reading every span in order and
    concatenating reconstructs ``npages`` pages, under either address unit.
    """
    ppf = pages_per_frame(addr_unit)
    step = ppf * PAGE_BYTES
    plan = []
    page = 0
    while page < npages:
        take = min(ppf, npages - page)
        spans = [(j * PAGE_BYTES * addr_unit, PAGE_BYTES) for j in range(take)]
        plan.append((base + page * PAGE_BYTES, spans))
        page += take
    return plan


def destride(frames, plan):
    """Assemble pages from 256 B frames according to ``frame_plan``."""
    if len(frames) != len(plan):
        raise ValueError("frame count %d != plan %d" % (len(frames), len(plan)))
    out = bytearray()
    for frame, (_cmd, spans) in zip(frames, plan):
        if len(frame) != FRAME_BYTES:
            raise ValueError("frame length %d != %d" % (len(frame), FRAME_BYTES))
        for off, nbytes in spans:
            out.extend(frame[off:off + nbytes])
    return bytes(out)


def feat_slots_to_bytes(raw):
    """Drop the high byte of every 16-bit feat slot ({8'h00, feat_data})."""
    if len(raw) % FEAT_SLOT_BYTES:
        raise ValueError("feat slot stream length %d is not even" % len(raw))
    return bytes(raw[0::FEAT_SLOT_BYTES])


def pages_for(nbytes, page_bytes=PAGE_BYTES):
    if nbytes % page_bytes:
        raise ValueError("%d bytes is not a whole number of pages" % nbytes)
    return nbytes // page_bytes


def frame_count(npages, addr_unit=PROD_ADDR_UNIT):
    return len(frame_plan(0, npages, addr_unit))
