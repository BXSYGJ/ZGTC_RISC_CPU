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
