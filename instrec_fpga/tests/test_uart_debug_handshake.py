"""Cycle model of the uart_debug -> uart_tx byte handshake (2026-10-29).

Board evidence: flashing the full NPU bitstream printed ``ITCO`` for
``INSTREC BOOT`` and ``D3ETT.D3R@FF`` for ``DDR3 SELFTEST...``.  Both are
exactly the ROM characters at index 0, 3, 6, 9 ...: uart_debug advanced
``rom_idx`` on every cycle where ``tx_byte_ready`` was high, but its
``tx_byte_valid`` was a single-cycle strobe that only reached uart_tx one
cycle later.  uart_tx was already busy by then, so it dropped the byte
while uart_debug kept the index moving.

The fix makes ``tx_byte_valid`` a level handshake: it is loaded once and
held until uart_tx accepts it, and the index/state advance is moved into
that handshake branch.

The model below mirrors the RTL register semantics exactly (non-blocking
updates read the old value, uart_tx accepts only in its ``!busy`` branch):

  * the fixed variant must deliver every ROM character in order;
  * the old strobe variant must reproduce the on-board loss signature
    (indices 0, 3, 6, 9 ...).

Neither needs a simulator, PDS or a board.
"""

from __future__ import annotations

BOOT = b'INSTREC BOOT\n'
BAUD = 12          # small stand-in for 1085; only the ratio matters


class TxCore:
    """uart_tx.v: busy/byte_wready/bit_idx/div_cnt."""

    def __init__(self, baud=BAUD):
        self.baud = baud
        self.busy = 0
        self.wready = 0
        self.bit = 0
        self.div = 0
        self.out = bytearray()

    def step(self, wvalid, wdata):
        """One clock. Returns True if this cycle accepted a byte."""
        accept = bool(wvalid and self.wready and not self.busy)
        nxt_wready = 0 if self.busy else 1
        if not self.busy:
            if accept:
                self.busy = 1
                self.bit = 0
                self.div = 0
                self.out.append(wdata)
        else:
            if self.div == self.baud - 1:
                self.div = 0
                if self.bit == 9:          # START + 8 data + STOP
                    self.busy = 0
                else:
                    self.bit += 1
            else:
                self.div += 1
        self.wready = nxt_wready
        return accept


def _run(mode, line, baud=BAUD, limit=2000000):
    """mode 'level' = fixed RTL, 'strobe' = old single-cycle RTL."""
    tx = TxCore(baud)
    valid = 0
    data = 0
    idx = 0
    seen = []
    for _ in range(limit):
        accepted = tx.step(valid, data)
        if accepted:
            seen.append(idx)
        ready_now = tx.wready

        if mode == 'level':
            # RTL: if (!valid) load; else if (ready) clear + advance.
            if not valid:
                valid, data = 1, line[idx]
            elif accepted:
                valid = 0
                if idx == len(line) - 1:
                    break
                idx += 1
        else:
            # RTL: valid <= 0 unconditionally, then valid <= 1 when ready,
            # and idx advances on ready (one cycle before the byte arrives).
            # The real RTL also returns to ST_IDLE once the last index is
            # passed, so the model stops loading beyond the line end.
            if ready_now and idx < len(line):
                valid, data = 1, line[idx]
                idx += 1
            else:
                valid = 0
                if idx >= len(line):
                    break
    return bytes(tx.out), seen


def test_level_handshake_delivers_every_character():
    out, seen = _run('level', BOOT)
    assert out == BOOT
    assert seen == list(range(len(BOOT)))


def test_old_strobe_reproduces_the_board_loss():
    out, seen = _run('strobe', BOOT)
    assert out != BOOT
    assert len(out) < len(BOOT), seen
    # signature of the bug: the ROM index advances by more than one between
    # accepted bytes, so whole characters are skipped (board printed ITCO
    # for INSTREC BOOT, i.e. a constant stride > 1).
    strides = {b - a for a, b in zip(seen, seen[1:])}
    assert strides and min(strides) > 1, (seen, strides)


def test_level_handshake_long_line():
    line = b'DDR3 SELFTEST...\n'
    out, seen = _run('level', line)
    assert out == line
    assert seen == list(range(len(line)))