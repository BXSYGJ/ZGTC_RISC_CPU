"""Native PG200 programming and UART capture; inspect is the default action."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def unpack_serial(payload: dict) -> bytes:
    """Decode the platform's hex payload without recording authentication data."""
    body = payload if "hex" in payload else payload.get("data", payload)
    if isinstance(body, dict):
        for key in ("hex", "dataHex", "hexData"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return bytes.fromhex(value.replace(" ", ""))
        for key in ("data", "text", "data_text"):
            value = body.get(key)
            if isinstance(value, str):
                return value.encode("utf-8", errors="replace")
    if isinstance(body, str):
        return body.encode("utf-8", errors="replace")
    return b""


def inspect(client) -> dict:
    devices = client.device_catalog()
    current = client.current_device()
    return {
        "devices": [{k: d.get(k) for k in ("id", "name", "board_model", "status")} for d in devices],
        "current_device_id": current.get("device_id") if current else None,
    }


def analyze_capture(raw: bytes | bytearray, *, passes: int = 2) -> dict:
    """Require complete BEGIN / CRC / PASS records with consecutive sequences."""
    if passes < 1:
        raise ValueError("passes must be positive")
    begin = re.compile(rb"PACERV_SHARED BEGIN seq=([0-9a-fA-F]{8}) RV32IMC ([0-9]+)MHz physical-DDR3")
    metrics = re.compile(rb"ISA=RV32IMC MASK=SB_SH CRC=([0-9a-fA-F]{8}) EXPECT=([0-9a-fA-F]{8}) ERR=([0-9a-fA-F]{8})")
    active = None
    errors = []
    runs = []
    complete = valid = streak = longest = incomplete = 0
    previous = None
    offset = 0
    for source_line in bytes(raw).splitlines(keepends=True):
        position = offset
        offset += len(source_line)
        if not source_line.endswith(b"\n"):
            continue  # A partial UART line is completed by a later packet.
        line = source_line.rstrip(b"\r\n")
        match = begin.fullmatch(line)
        if match:
            if active:
                incomplete += 1
                streak = 0
            active = {"sequence": int(match[1], 16), "clock_mhz": int(match[2]),
                      "start_byte": position, "metrics": None}
            continue
        match = metrics.fullmatch(line)
        if match and active:
            if active["metrics"] is not None:
                errors.append({"kind": "duplicate_crc_line", "byte": position})
            active["metrics"] = {"crc": match[1].decode().upper(),
                                 "expected_crc": match[2].decode().upper(),
                                 "error_count": int(match[3], 16)}
            continue
        if line.startswith(b"PACERV_SHARED FAIL"):
            errors.append({"kind": "firmware_fail", "byte": position,
                           "line": line.decode("ascii", errors="replace")})
            if active:
                runs.append({**active, "end_byte": offset, "valid": False})
            active = None
            streak = 0
            previous = None
            continue
        if line != b"PACERV_SHARED PASS":
            continue
        if not active:
            # Late serial opening may leave a tail before the next BEGIN.
            continue
        values = active["metrics"]
        issues = []
        if values is None:
            issues.append("missing_crc_line")
        else:
            if values["crc"] != values["expected_crc"]:
                issues.append("crc_mismatch")
            if values["error_count"] != 0:
                issues.append("nonzero_error_count")
            complete += 1
        if previous is not None and active["sequence"] != ((previous + 1) & 0xffffffff):
            issues.append("sequence_discontinuity")
        good = not issues
        for kind in issues:
            errors.append({"kind": kind, "sequence": active["sequence"], "byte": position})
        record = {k: v for k, v in active.items() if k != "metrics"}
        record.update(values or {})
        record.update({"end_byte": offset, "valid": good})
        runs.append(record)
        if good:
            valid += 1
            streak += 1
            longest = max(longest, streak)
            previous = active["sequence"]
        else:
            streak = 0
            previous = None
        active = None
    if active:
        incomplete += 1
    return {"required_passes": passes, "complete_runs": complete, "valid_runs": valid,
            "consecutive_passes": streak, "longest_consecutive_passes": longest,
            "incomplete_runs": incomplete, "runs": runs, "errors": errors,
            "matched": streak >= passes and not errors}


def capture(client, bitstream: Path, output: Path, *, seconds: float = 90,
            baud: int = 115200, minutes: int = 10, expected: str = "PACERV_SHARED PASS",
            send_text: str = "", clock_hz: int = 125000000, passes: int = 2) -> dict:
    if passes < 1:
        raise ValueError("passes must be positive")
    if expected != "PACERV_SHARED PASS":
        raise ValueError("This harness requires complete PACERV_SHARED records.")
    if client.current_device():
        raise RuntimeError("An existing reservation is active; this run leaves it untouched.")
    bitstream = bitstream.resolve(strict=True)
    if bitstream.suffix.lower() != ".sbit":
        raise ValueError("Expected a PDS .sbit file.")
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "target": "PG2L200H-6FBB676", "clock_hz": clock_hz, "baud": baud,
        "bitstream": str(bitstream), "bitstream_sha256": hashlib.sha256(bitstream.read_bytes()).hexdigest(),
        "expected": expected, "bytes": 0, "matched": False, "released": False,
        "evidence": "real PG200 CPU / physical DDR3 / UART; synthetic competing master",
    }
    device_id = None
    reservation_attempted = False
    serial_opened = False
    raw = bytearray()
    try:
        reservation_attempted = True
        reservation = client.reserve(minutes=minutes, card_type="with_camera")
        current = client.current_device()
        device_id = (current or {}).get("device_id") or reservation.get("device_id") or reservation.get("deviceId")
        if not device_id:
            raise RuntimeError("Reservation did not expose a device id.")
        if (current or {}).get("board_model") not in (None,"PG2L200H"):
            raise RuntimeError("The allocated device does not match the PG200 bitstream.")
        result["device_id"] = int(device_id)
        result["device_name"] = (current or {}).get("device_name")
        client.burn_and_wait(int(device_id), bitstream)
        result["programmed"] = True
        client.serial_open(int(device_id), baud=baud)
        serial_opened = True
        if send_text:
            client.serial_send(int(device_id), send_text, mode="text")
        deadline = time.monotonic() + seconds
        with (output / "capture.jsonl").open("w", encoding="utf-8") as log:
            while time.monotonic() < deadline:
                packet = unpack_serial(client.serial_read(int(device_id), length=512))
                if packet:
                    raw.extend(packet)
                    log.write(json.dumps({"elapsed_s": seconds - max(0, deadline - time.monotonic()), "hex": packet.hex()}, ensure_ascii=True) + "\n")
                    log.flush()
                    result.update(analyze_capture(raw, passes=passes))
                    if result["matched"] or result["errors"]:
                        break
                else:
                    time.sleep(0.15)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        # Platform exceptions can contain HTTP request metadata. Keep secrets out of evidence.
        raise
    finally:
        try:
            if serial_opened:
                client.serial_close(int(device_id))
        finally:
            try:
                if device_id is None and reservation_attempted:
                    remaining = client.current_device()
                    device_id = (remaining or {}).get("device_id")
                if device_id is not None:
                    client.release(int(device_id))
                    result["released"] = True
            finally:
                result.update(analyze_capture(raw, passes=passes))
                result["bytes"] = len(raw)
                (output / "capture.bin").write_bytes(raw)
                (output / "capture.txt").write_text(raw.decode("utf-8", errors="replace"), encoding="utf-8")
                (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("inspect", "run"), default="inspect")
    parser.add_argument("--bitstream", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--account", type=Path)
    parser.add_argument("--lab-root", type=Path, default=repository_root() / "tool" / "fpga_lab")
    parser.add_argument("--seconds", type=float, default=90)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--minutes", type=int, choices=(10, 20, 30), default=10)
    parser.add_argument("--clock-hz", type=int, default=125000000)
    parser.add_argument("--expected", default="PACERV_SHARED PASS")
    parser.add_argument("--passes", type=int, default=2, help="number of complete consecutive zero-error runs required")
    parser.add_argument("--send-text", default="")
    args = parser.parse_args()
    if args.passes < 1:
        parser.error("--passes must be at least 1")
    if args.action == "run" and (not args.bitstream or not args.output):
        parser.error("run requires --bitstream and --output")
    sys.path.insert(0, str(args.lab_root.resolve(strict=True)))
    from fpga_lab_server.platform import PlatformClient
    from fpga_lab_server.paths import ACCOUNT_FILE
    client = PlatformClient()
    try:
        client.relogin_from_account(args.account or ACCOUNT_FILE)
        if args.action == "inspect":
            print(json.dumps(inspect(client), indent=2, ensure_ascii=True))
            return 0
        result = capture(client, args.bitstream, args.output, seconds=args.seconds, baud=args.baud,
                         minutes=args.minutes, expected=args.expected, send_text=args.send_text,
                         clock_hz=args.clock_hz, passes=args.passes)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0 if result["matched"] and result["released"] else 2
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("REMOTE_CAPTURE_ERROR " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
