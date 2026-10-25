"""Validate physical bindings and frame a complete fresh Embench UART response."""
import json
from pathlib import Path
import re
import run_embench as h
from audit_physical_timing import audit


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def physical_binding(physical, workload):
    physical = Path(physical).resolve()
    if not physical.is_relative_to((h.ROOT / 'results').resolve()): raise ValueError('Physical run outside results')
    pm = read(physical / 'manifest.json')
    if (physical / 'qualification-correction.json').exists(): raise ValueError('Superseded or rejected qualification')
    allowed_protocol = pm.get('protocol') == 'v25' or (pm.get('protocol') == 'v26' and workload == 'uart-loader')
    if not allowed_protocol or pm['status'] != 'internal_timing_passed' or pm['variant'] != 'embench_' + workload:
        raise ValueError('Unqualified Embench implementation')
    if pm['configured_clock_hz'] != 153000000 or pm['firmware']['workload'] != workload:
        raise ValueError('Physical clock/workload mismatch')
    return physical_artifacts_binding(physical,pm)


def physical_artifacts_binding(physical,pm):
    """Validate common immutable artifacts after caller-specific identity checks."""
    for relative, expected in read(physical / 'source-hashes.json').items():
        if h.sha(physical / 'inputs' / relative) != expected: raise ValueError('Changed physical source: ' + relative)
    for relative, expected in read(physical / 'implementation/input-hashes.json').items():
        if h.sha(physical / 'implementation' / relative) != expected: raise ValueError('Changed implementation input')
    # This file exists only after native inserter output has passed the original mapping validator.
    if pm.get('instrumentation_profile') == 'none':
        from physical_instrumentation import audit_no_ila
        checked = audit_no_ila(physical, pm)
        if checked != pm.get('instrumentation_audit') or checked != read(physical / 'implementation/instrumentation-audit.json'):
            raise ValueError('ILA-free audit differs')
    else:
        mapping = read(physical / 'implementation/mapping-audit.json')
        for key, value in dict(data_channels=42,trigger_channels=33,depth=1024,clock='cpu_clk',full_ex_pc_preserved=True).items():
            if mapping.get(key) != value: raise ValueError('Incorrect ILA mapping: '+key)
    for relative, expected in pm['output_hashes'].items():
        if h.sha(physical / relative) != expected: raise ValueError('Physical output changed: '+relative)
    if h.sha(physical / 'inputs/firmware.hex') != pm['firmware']['firmware_sha256']:
        raise ValueError('Firmware identity changed')
    bit = physical / 'implementation/generate_bitstream/pds_soc_top.sbit'
    if h.sha(bit) != pm['bitstream_sha256']: raise ValueError('Changed bitstream')
    timing = audit(physical)
    if not timing['internal_multicorner_timing_passed']: raise ValueError('Timing failed')
    from run_physical_ila import load_module, text
    report=load_module(physical/'inputs/tools/pds_report.py','bound_embench_report').parse_ila_reports(
        text(physical/'implementation/report_timing/pds_soc_top.rtr'),text(physical/'implementation/run.log'),153000000)
    if report != pm['report']: raise ValueError('Native resource/clock evidence differs')
    return pm, timing


def parse_frame(raw, workload):
    start = 'EMBENCH START ' + workload + ' heat=1 scale=1 clock_hz=153000000\n'
    finish = 'EMBENCH FINISHED ' + workload + '\n'
    normalized = raw.replace('\r\n', '\n')
    if normalized.count(start) != 1 or normalized.count(finish) != 1: raise ValueError('Missing/duplicate workload framing')
    offset = normalized.index(start)
    if any(c not in '\x00\r\n\t ' for c in normalized[:offset]): raise ValueError('Unrecognized leading UART content')
    frame = normalized[offset:]
    pattern = re.escape(start) + r'EMBENCH cycles=0x([0-9a-f]{16}) retired=0x([0-9a-f]{16}) verified=([01])\n' + re.escape(finish)
    matched = re.fullmatch(pattern, frame)
    if not matched: raise ValueError('Malformed or extra UART content')
    cycles, retired = (int(x, 16) for x in matched.groups()[:2])
    if matched[3] != '1' or not 0 < retired <= cycles < 2**64: raise ValueError('Correctness/counters failed')
    return dict(workload=workload, cycles=cycles, retired_instructions=retired, cpi=cycles/retired,
                correctness=True, configured_clock_hz=153000000, measured_clock_hz=None,
                seconds_from_configured_clock=cycles/153000000,
                leading_padding_characters=offset), frame
