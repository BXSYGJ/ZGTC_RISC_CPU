"""Compare a known UART control and the clock probe on the same reservation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT.parent / 'tool/fpga_lab'))
from fpga_lab_server.platform import PlatformClient
from remote_capture import unpack_serial


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--account', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for path in (args.probe, args.control, args.account):
        if not path.is_file():
            raise FileNotFoundError(path)
    args.output.mkdir(parents=True, exist_ok=False)
    client = PlatformClient()
    device = None
    attempted = False
    opened = False
    report = {'scope': 'same-device UART transport diagnostic', 'released': False,
              'runs': []}
    try:
        client.relogin_from_account(args.account)
        if client.current_device():
            raise RuntimeError('An existing reservation is retained')
        attempted = True
        client.reserve(minutes=10, card_type='with_camera')
        current = client.current_device() or {}
        device = current.get('device_id')
        if not device:
            raise RuntimeError('No reserved device')
        report['device_id'] = device
        report['device_name'] = current.get('device_name')
        for label, bit, bauds in (('control', args.control, (9600,)),
                                   ('probe', args.probe, (115200, 9600))):
            burn = client.burn_and_wait(int(device), bit)
            for baud in bauds:
                raw = bytearray()
                prefix = args.output / f'{label}-{baud}'
                run = {'label': label, 'baud': baud,
                       'bitstream': str(bit.resolve()),
                       'sha256': hashlib.sha256(bit.read_bytes()).hexdigest(),
                       'burn_complete': burn.get('isComplete'), 'bytes': 0}
                report['runs'].append(run)
                client.serial_open(int(device), baud=baud)
                opened = True
                if label == 'control':
                    client.serial_send(int(device), 'G', mode='text')
                until = time.monotonic() + (35 if label == 'control' else 6)
                with prefix.with_suffix('.jsonl').open('w', encoding='utf-8') as log:
                    while time.monotonic() < until:
                        packet = client.serial_read(int(device), length=512)
                        decoded = unpack_serial(packet)
                        if decoded:
                            raw.extend(decoded)
                            log.write(json.dumps({'hex': decoded.hex()}) + '\n')
                            log.flush()
                        else:
                            time.sleep(.15)
                client.serial_close(int(device))
                opened = False
                prefix.with_suffix('.bin').write_bytes(raw)
                prefix.with_suffix('.txt').write_text(raw.decode('ascii', errors='replace'), encoding='utf-8')
                run['bytes'] = len(raw)
                print(json.dumps(run), flush=True)
    finally:
        try:
            if opened:
                client.serial_close(int(device))
        finally:
            try:
                if device is None and attempted:
                    device = (client.current_device() or {}).get('device_id')
                if device is not None:
                    client.release(int(device))
                    report['released'] = True
            finally:
                client.close()
                (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
