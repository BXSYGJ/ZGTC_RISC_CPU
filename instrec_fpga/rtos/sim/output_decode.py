"""Decode UTF-8 tool logs containing Windows WSL UTF-16 diagnostic lines."""
from __future__ import annotations

import re


_WSL_LINE = re.compile(
    rb"(?:\xff\xfe)?w\x00s\x00l\x00:\x00|(?:\xfe\xff)?\x00w\x00s\x00l\x00:"
)


def decode_mixed_output(raw: bytes) -> str:
    """Preserve UTF-8 output and each separately encoded WSL diagnostic.

    wsl.exe writes its own ``wsl:`` lines as UTF-16 while the Linux process
    writes UTF-8 to the same pipe. Each Windows diagnostic ends at its aligned
    UTF-16 LF (or EOF for a partial final line). Decoding those spans separately
    preserves both the Chinese message and the compiler warnings, including
    their original line endings. No bytes are replaced or filtered.

    A standalone BOM-marked UTF-16 stream also retains its normal decoding.
    Unknown or incomplete encodings raise an error so the unchanged raw log
    remains the diagnostic source, instead of recording replacement glyphs.
    """
    if not raw:
        return ""
    match = _WSL_LINE.search(raw)
    if match is None:
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8")
    else:
        pieces = []
        cursor = 0
        while match is not None:
            pieces.append(raw[cursor:match.start()].decode("utf-8"))
            start = match.start()
            big_endian = raw[start:start + 2] in (b"\xfe\xff", b"\x00w")
            if raw[start:start + 2] in (b"\xff\xfe", b"\xfe\xff"):
                start += 2
            newline = b"\x00\n" if big_endian else b"\n\x00"
            end = raw.find(newline, start)
            while end != -1 and (end - start) % 2:
                end = raw.find(newline, end + 1)
            end = len(raw) if end == -1 else end + 2
            pieces.append(raw[start:end].decode("utf-16-be" if big_endian else "utf-16-le"))
            cursor = end
            match = _WSL_LINE.search(raw, cursor)
        pieces.append(raw[cursor:].decode("utf-8"))
        text = "".join(pieces)
    if "\x00" in text:
        raise UnicodeError("Unexpected NUL in process output; inspect the preserved raw log for an unrecognized encoding")
    return text
