import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--bytes", type=int, default=16384)
    args = parser.parse_args()
    image = args.source.read_bytes()
    if args.bytes <= 0 or args.bytes % 4 or len(image) > args.bytes:
        raise ValueError("Image does not fit the positive, word-aligned memory size")
    image += bytes(args.bytes - len(image))
    words = [f"{int.from_bytes(image[offset:offset + 4], 'little'):08x}" for offset in range(0, len(image), 4)]
    args.destination.write_text("\n".join(words) + "\n", encoding="ascii")
    print(f"Converted {args.source.name}: {len(words)} little-endian words")


if __name__ == "__main__":
    main()
