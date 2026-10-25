"""Frame a complete UART record while retaining only admissible leading padding."""
def extract_frame(raw):
    marker='ZGTC COREMARK START iterations='
    if raw.count(marker)!=1 or raw.count('ZGTC COREMARK FINISHED')!=1:
        raise ValueError('Expected one complete CoreMark UART frame')
    offset=raw.index(marker)
    if any(character not in '\x00\r\n\t ' for character in raw[:offset]):
        raise ValueError('Unexpected content before CoreMark start marker')
    return raw[offset:], {'leading_padding_characters':offset,'leading_nul_characters':raw[:offset].count('\x00'),'scope':'Only NUL/whitespace before the unique start marker excluded; no benchmark bytes repaired or reordered.'}
