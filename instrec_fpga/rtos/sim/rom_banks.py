"""Create and validate word-addressed even/odd instruction ROM images."""
from __future__ import annotations

from pathlib import Path
import re


def read_words(path: Path, count: int) -> list[int]:
    """Read known 32-bit readmemh values, including @ word-address directives.

    Unspecified words retain the zero initialization used by the RTL. Address
    directives change the word cursor; comments and line breaks do not consume
    memory locations. Later writes to an address replace earlier values.
    """
    if count < 1:
        raise ValueError("ROM word count must be positive")
    text = path.read_text(encoding="ascii")
    text = re.sub(r"/\*.*?\*/|//[^\n]*", " ", text, flags=re.DOTALL)
    words = [0] * count
    address = 0
    for token in text.split():
        value = token.replace("_", "")
        if value.startswith("@"):
            if not re.fullmatch(r"@[0-9a-fA-F]+", value):
                raise ValueError(f"Invalid readmemh address in {path}: {token}")
            address = int(value[1:], 16)
            if not 0 <= address < count:
                raise ValueError(f"readmemh address outside {count}-word ROM: {token}")
        else:
            if not re.fullmatch(r"[0-9a-fA-F]{1,8}", value):
                raise ValueError(f"Expected a known 32-bit readmemh word in {path}: {token}")
            if address >= count:
                raise ValueError(f"readmemh data exceeds {count}-word ROM: {path}")
            words[address] = int(value, 16)
            address += 1
    return words


def split_rom(source: Path, count: int) -> tuple[Path, Path]:
    """Emit dense banks indexed by full-image word address divided by two."""
    if count % 2:
        raise ValueError("Even/odd ROM banks require an even word count")
    words = read_words(source, count)
    paths = tuple(source.with_name(source.stem + suffix + source.suffix)
                  for suffix in ("_even", "_odd"))
    for parity, path in enumerate(paths):
        path.write_text("".join(f"{word:08x}\n" for word in words[parity::2]), encoding="ascii")
    validate_banks(source, *paths, count)
    return paths


def validate_banks(source: Path, even: Path, odd: Path, count: int) -> None:
    """Check actual bank files against the full ROM's addressed contents."""
    if count % 2:
        raise ValueError("Even/odd ROM banks require an even word count")
    words = read_words(source, count)
    for parity, path in enumerate((even, odd)):
        bank = read_words(path, count // 2)
        expected = words[parity::2]
        if bank != expected:
            index = next(i for i, pair in enumerate(zip(bank, expected)) if pair[0] != pair[1])
            raise ValueError(f"ROM bank mismatch at full word address {index * 2 + parity:#x}: {path}")
