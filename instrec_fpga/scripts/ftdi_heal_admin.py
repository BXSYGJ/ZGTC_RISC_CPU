# ftdi_heal_admin.py — FTDI FT2232H auto-recovery (admin-only).
#
# Recovery sequence:
#   1. Kill zombie cdt_js / cdt_cfg (D2XX handle leaked, nobody else can hold it)
#   2. USB relay VBUS pulse-bounce (hardest recovery, only works if relay present)
#      → if relay not found: skip (graceful fallback)
#   3. pnputil /scan-devices (mild PnP rescan)
#   4. Remove all VID_0403 phantom devnodes accumulated since last reboot
#      → these are Status=Unknown objects left over from hung FT2232H enumeration
#   5. Final pnputil /scan-devices (force full re-enumeration after phantom cleanup)
#   6. If FTDI present: auto-start cdt_js -port 65420
#
# Run as: python scripts/ftdi_heal_admin.py
# Run on schedule: Windows Task "FTDI Auto-Heal (instrec)" every 5 min (HIGHEST).
# Evidence log: instrec_fpga/build/heal_logs/ftdi_heal.log
#
# Beethoven A36D constraint: xHCI + RootHub30 both flagged "critical system
# device" → pnputil /disable-device /restart-device both exit=-536870351
# (Cannot disable critical system device). So the ONLY working software
# recovery on this machine is the relay-based VBUS pulse-bounce.
# Fallback (no relay): kill zombies + remove phantoms + rescan (weak).

import subprocess, sys, os, time, glob, datetime, traceback

LOG_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'heal_logs')
LOG_FILE = os.path.join(LOG_DIR, 'ftdi_heal.log')

def Log(msg):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return -1, 'TIMEOUT'
    except FileNotFoundError:
        return -2, f'NOT FOUND: {cmd[0]}'

def ftdi_present():
    """Returns (present_count, total_count)."""
    code, out = run(['powershell', '-NoProfile', '-Command',
        "(Get-PnpDevice -PresentOnly -EA SilentlyContinue | Where-Object {$_.InstanceId -match 'VID_0403'} | Measure-Object).Count; "
        "(Get-PnpDevice -EA SilentlyContinue | Where-Object {$_.InstanceId -match 'VID_0403'} | Measure-Object).Count"])
    if code != 0:
        return 0, 0
    parts = out.strip().splitlines()
    try:
        return int(parts[0]), int(parts[1])
    except Exception:
        return 0, 0

def kill_cdt():
    code, out = run(['taskkill', '/F', '/IM', 'cdt_js.exe', '/T'])
    code2, out2 = run(['taskkill', '/F', '/IM', 'cdt_cfg.exe', '/T'])
    Log(f'kill cdt_js/cdt_cfg: {out.strip()[:120]}')

def pnputil(args):
    code, out = run(['pnputil.exe'] + args, timeout=30)
    return code, out.strip()[:300]

def remove_phantoms():
    code, out = run(['powershell', '-NoProfile', '-Command',
        "$(Get-PnpDevice -EA SilentlyContinue | Where-Object {$_.InstanceId -match 'VID_0403'} | Select-Object -ExpandProperty InstanceId -Unique)"])
    if code != 0:
        Log(f'  enumerate phantoms failed: {out[:100]}')
        return 0
    ids = [l.strip() for l in out.splitlines() if 'VID_0403' in l]
    if not ids:
        Log('  no VID_0403 phantom devnodes found')
        return 0
    removed = 0
    for iid in ids:
        c, o = pnputil(['/remove-device', iid])
        if c == 0:
            removed += 1
        time.sleep(0.3)
    Log(f'  removed {removed}/{len(ids)} VID_0403 phantom devnodes')
    return removed

def relay_pulse():
    """Try VBUS pulse-bounce via USB relay board. Returns True if executed."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import usb_relay
        port = usb_relay.find_relay_port()
        if not port:
            Log('  USB relay not found → skip VBUS pulse')
            return False
        Log(f'  USB relay found on {port} → pulse-bounce VBUS')
        usb_relay.pulse_bounce(port=port, verbose=False)
        Log('  VBUS cut+restore done, waiting 8s for re-enumeration')
        time.sleep(8)
        return True
    except Exception as e:
        Log(f'  relay pulse failed: {e}')
        return False

def start_cdt_js():
    if any('cdt_js' in p.lower() for p in subprocess.run(['tasklist'], capture_output=True, text=True).stdout):
        Log('  cdt_js already alive')
        return
    pds_root = os.environ.get('PDS_ROOT', r'H:\GG\pango\PDS_2022.2-SP6.4')
    exe = os.path.join(pds_root, 'bin', 'cdt_js.exe')
    if not os.path.exists(exe):
        Log(f'  cdt_js not found at {exe}')
        return
    DETACHED = 0x00000008
    subprocess.Popen([exe, '-port', '65420'], creationflags=DETACHED)
    Log(f'  cdt_js started on :65420')
    time.sleep(2)

def main():
    Log('=' * 50)
    p0, t0 = ftdi_present()
    Log(f'HEAL START: present={p0} total={t0}')

    if p0 > 0:
        Log('FTDI already present → nothing to heal')
        start_cdt_js()
        return 0

    kill_cdt()
    relay_pulse()
    Log('pnputil /scan-devices...')
    pnputil(['/scan-devices'])
    time.sleep(3)

    p1, t1 = ftdi_present()
    Log(f'after scan: present={p1} total={t1}')

    if p1 == 0:
        Log('removing VID_0403 phantom devnodes...')
        remove_phantoms()
        Log('final pnputil /scan-devices...')
        pnputil(['/scan-devices'])
        time.sleep(8)

    p2, t2 = ftdi_present()
    Log(f'FINAL: present={p2} total={t2}')

    if p2 > 0:
        start_cdt_js()
    else:
        Log('HEAL FAILED — FTDI still absent (relay or physical re-seat required)')

    return 0 if p2 > 0 else 1

if __name__ == '__main__':
    sys.exit(main())
