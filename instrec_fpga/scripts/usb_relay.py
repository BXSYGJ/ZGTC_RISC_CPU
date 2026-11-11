"""
usb_relay.py — Serial-control USB relay board (CH341 driver, 9600 bps)
Protocol from board docs (4-byte frames, checksum = sum(low 8 bits)):

    [0xA0][addr][op][(0xA0+addr+op) & 0xFF]

    op=0x00 close (off)   no-feedback
    op=0x01 open  (on)    no-feedback
    op=0x02 close (off)   with feedback  → reply A0 addr 00 AA
    op=0x03 open  (on)    with feedback  → reply A0 addr 01 AB
    op=0x04 toggle        with feedback
    op=0x05 query state   → reply A0 addr XX YY
    op=0x06 pulse-bounce  with feedback  → open→close atomically

Recovery flow (for FTDI FT2232H USB PHY hang):
    pulse_bounce() → VBUS cut for ~1 s → FT2232H re-enumerates automatically.

Author: InstRec-FPGA heal system, 2026-11-11
"""
import serial, time, sys, glob

RELAY_BAUD = 9600
RELAY_START = 0xA0

def _frame(addr, op):
    """Build 4-byte relay frame."""
    ck = (RELAY_START + addr + op) & 0xFF
    return bytes([RELAY_START, addr, op, ck])

def find_relay_port():
    """Auto-scan COM ports for relay (CH341 + signature A0 01 XX)."""
    import serial.tools.list_ports as lp
    candidates = []
    for p in lp.comports():
        # CH341 devices show as USB-SERIAL CH340 or similar
        if 'CH341' in (p.description or '') or 'CH340' in (p.description or '') or 'USB Serial' in (p.description or ''):
            candidates.append(p.device)
        # Fallback: not COM5 (that's CP2102 CP210x for UART debug)
        if 'CP210x' in (p.description or '') or 'CP2102' in (p.description or ''):
            continue
    if candidates:
        return candidates[0]
    # Brute force: try every COM except CP2102
    for port in glob.glob('COM*'):
        if port.upper() == 'COM5':
            continue
        try:
            with serial.Serial(port, RELAY_BAUD, timeout=0.3) as s:
                s.write(_frame(0x01, 0x05))  # query state
                rsp = s.read(4)
                if len(rsp) == 4 and rsp[0] == 0xA0:
                    return port
        except Exception:
            pass
    return None

def _open(port, addr=1):
    s = serial.Serial(port, RELAY_BAUD, timeout=0.5)
    s.write(_frame(addr, 0x02))  # close with feedback
    time.sleep(0.1)
    rsp = s.read(4)
    s.close()
    return rsp

def relay_close(port=None, addr=1, verbose=True):
    """Cut VBUS (relay OFF = no power to FT2232H)."""
    if port is None: port = find_relay_port()
    if not port:
        raise RuntimeError('USB relay port not found')
    rsp = _open(port, addr)
    if verbose: print(f'[relay] CUT VBUS addr{addr} port={port} rsp={rsp.hex() if rsp else "NONE"}')
    return port

def relay_open(port=None, addr=1, verbose=True):
    """Restore VBUS (relay ON = power to FT2232H)."""
    if port is None: port = find_relay_port()
    if not port:
        raise RuntimeError('USB relay port not found')
    s = serial.Serial(port, RELAY_BAUD, timeout=0.5)
    s.write(_frame(addr, 0x03))  # open with feedback
    time.sleep(0.1)
    rsp = s.read(4)
    s.close()
    if verbose: print(f'[relay] RESTORE VBUS addr{addr} port={port} rsp={rsp.hex() if rsp else "NONE"}')
    return port

def pulse_bounce(port=None, addr=1, cut_seconds=1.0, verbose=True):
    """Atomic VBUS pulse: cut → sleep → restore. Uses board's 0x06 if available,
    falls back to explicit close→sleep→open otherwise."""
    if port is None: port = find_relay_port()
    if not port:
        raise RuntimeError('USB relay port not found')
    # Try 0x06 (pulse-bounce with feedback) — board handles timing itself
    try:
        s = serial.Serial(port, RELAY_BAUD, timeout=1.0)
        s.write(_frame(addr, 0x06))
        time.sleep(2.0)
        rsp = s.read(4)
        s.close()
        if len(rsp) == 4 and rsp[0] == 0xA0:
            if verbose: print(f'[relay] PULSE-BOUNCE (0x06 OK) addr{addr} port={port} rsp={rsp.hex()}')
            return port
    except Exception:
        pass
    # Fallback: explicit sequence
    if verbose: print(f'[relay] explicit close→{cut_seconds}s→open port={port}')
    relay_close(port, addr, verbose=False)
    time.sleep(cut_seconds)
    relay_open(port, addr, verbose=False)
    if verbose: print(f'[relay] DONE VBUS cut+restore addr{addr}')
    return port

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'find':
        port = find_relay_port()
        print(f'RELAY_PORT={port}')
    elif cmd == 'status':
        port = find_relay_port()
        if not port:
            print('RELAY_PORT=NONE')
            sys.exit(2)
        s = serial.Serial(port, RELAY_BAUD, timeout=0.5)
        s.write(_frame(0x01, 0x05))
        time.sleep(0.1)
        rsp = s.read(4)
        s.close()
        state = {'00': 'CLOSED (VBUS off)', '01': 'OPEN (VBUS on)'}.get(rsp.hex()[4:6], 'unknown')
        print(f'RELAY port={port} state={state} raw={rsp.hex()}')
    elif cmd in ('cut', 'close', 'off'):
        relay_close()
    elif cmd in ('restore', 'open', 'on'):
        relay_open()
    elif cmd in ('pulse', 'bounce', 'reset'):
        pulse_bounce()
    else:
        print(f'Unknown cmd: {cmd}. Use: find | status | cut | restore | pulse')
