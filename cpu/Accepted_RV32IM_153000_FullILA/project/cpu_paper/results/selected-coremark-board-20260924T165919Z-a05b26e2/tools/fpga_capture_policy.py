"""Classify malformed UART evidence separately from correctness failures."""


class SerialCaptureError(RuntimeError):
    """Requires a separately recorded, fresh cold-programmed observation."""


def parse_capture(parser, *args):
    try:
        return parser(*args)
    except UnicodeDecodeError as error:
        raise SerialCaptureError('Non-ASCII UART capture') from error
    except ValueError as error:
        if str(error) in ('Control bytes in CoreMark frame','Unexpected control byte in benchmark frame'):
            raise SerialCaptureError(str(error)) from error
        if str(error).startswith('Expected exactly one field: '):
            raise SerialCaptureError('Incomplete or duplicated CoreMark field') from error
        raise
