"""native_target.py — native 直连专门预约 59/61，烧信标后读 20s，验证是否为桥接侧问题。"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpga_lab_server.paths import ACCOUNT_FILE
from fpga_lab_server.platform import PlatformClient

BEACON = Path("test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit")
TARGETS = {59, 61}


def main():
    pc = PlatformClient()
    cred = [ln.strip() for ln in ACCOUNT_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    pc.login(cred[0], cred[1])
    print("login ok")
    results = {}
    for rnd in range(1, 40):
        try:
            pc.release_current()
        except Exception:
            pass
        d = pc.reserve(10)
        box = d.get("deviceId")
        if box not in TARGETS:
            print(f"[{rnd}] skip box={box} ({d.get('deviceName')})")
            pc.release_current()
            continue
        pc.burn_and_wait(box, BEACON)
        print(f"[{rnd}] box={box} ({d.get('deviceName')}) burned", flush=True)
        try:
            st = pc.serial_open(box)
            print(f"  open drainedBytes={st.get('drainedBytes')}", flush=True)
        except Exception as e:
            print(f"  open ERROR {e}")
            results[box] = "OPEN_ERR"
            pc.release_current()
            continue
        got = empty = 0
        t0 = time.time()
        while time.time() - t0 < 20:
            time.sleep(0.7)
            rd = pc.serial_read(box, length=64)
            if rd.get("hasData") or rd.get("bytesRead"):
                got += 1
                if got == 1:
                    print(f"  first DATA hex={rd.get('hex')[:48]}", flush=True)
            else:
                empty += 1
        results[box] = "PASS" if got else "FAIL"
        print(f"[{rnd}] box={box} -> {results[box]} got={got} empty={empty}", flush=True)
        try:
            pc.serial_close(box)
            pc.release_current()
        except Exception:
            pass
        if len(results) >= len(TARGETS):
            break
    print("SUMMARY", results)
    try:
        pc.release_current()
    except Exception:
        pass
    pc.close()


if __name__ == "__main__":
    main()
