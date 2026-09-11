import argparse
import hashlib
import json
from pathlib import Path


DEVICE = "PG2L200H"
PACKING = "logicmatrix-msb0-descending-150"
BOUNDARY_BITS = 1079
BSDL_SHA256 = "e2379c425eba0f9ffdeaf7a73ac923ae9d8eb715c2274bb635c7e895aeba48fd"
SIGNALS = {
    "SCBV": {"pin": "AB15", "cell": 0, "kind": "input"},
    "KEY1": {"pin": "C23", "cell": 846, "kind": "bidir"},
    "UART_RX": {"pin": "AC26", "cell": 14, "kind": "bidir"},
    "UART_TX": {"pin": "AB26", "cell": 12, "kind": "bidir"},
}


def decode_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    if set(snapshot) != {"device", "packing", "origin", "rawFrame"}:
        raise ValueError("snapshot requires exactly device, packing, origin, rawFrame")
    if snapshot["device"] != DEVICE or snapshot["packing"] != PACKING:
        raise ValueError("unsupported device or packing; never infer device from frame length")
    if snapshot["origin"] not in ("synthetic", "unverified_capture"):
        raise ValueError("origin must be synthetic or unverified_capture")
    raw_frame = snapshot["rawFrame"]
    if not isinstance(raw_frame, list) or len(raw_frame) != 150:
        raise ValueError("this transport requires exactly 150 bytes, not a packed 135-byte BSR")
    if any(type(value) is not int or not 0 <= value <= 255 for value in raw_frame):
        raise ValueError("rawFrame values must be integer bytes (booleans are not bytes)")
    signals = {}
    for name, mapping in SIGNALS.items():
        bit_position = BOUNDARY_BITS - 1 - mapping["cell"]
        signals[name] = {
            **mapping,
            "byte_index": bit_position // 8,
            "bit_in_byte": 7 - bit_position % 8,
            "level": (raw_frame[bit_position // 8] >> (7 - bit_position % 8)) & 1,
        }
    return {
        "status": "offline_decoded_not_board_acceptance",
        "device": DEVICE,
        "packing": PACKING,
        "origin": snapshot["origin"],
        "boundary_bits": BOUNDARY_BITS,
        "frame_bytes": len(raw_frame),
        "raw_sha256": hashlib.sha256(bytes(raw_frame)).hexdigest(),
        "bsdl_sha256": BSDL_SHA256,
        "signals": signals,
        "uninterpreted_tail_bits": 121,
        "scan_instruction_verified": False,
        "capture_device_verified": False,
        "configuration_voltage_verified": False,
        "mechanical_key_actuation_verified": False,
    }


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description="Offline PG2L200H boundary snapshot decoder; never controls hardware")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        if args.snapshot.stat().st_size > 16384:
            raise ValueError("snapshot exceeds 16 KiB")
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"), object_pairs_hook=reject_duplicate_keys)
        print(json.dumps(decode_snapshot(snapshot), indent=2, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"FAIL boundary snapshot: {error}\n")


if __name__ == "__main__":
    main()
