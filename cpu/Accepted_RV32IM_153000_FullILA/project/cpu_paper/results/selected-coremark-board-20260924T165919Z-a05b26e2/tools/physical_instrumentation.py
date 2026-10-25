"""Explicit ILA-free implementation profile and independent absence checks.

The legacy physical runner remains available for historical reproduction.
Apply this transformation after its existing source/clock/profile adapters.
"""
import json
import re

from create_redirect_optimization import replace_once

NO_ILA = dict(enabled=False, data_channels=0, trigger_channels=0, depth=0, clock=None)
DEBUG_NET = re.compile(r'\bu_CORES\b|\bu_debug_core_\d+\b|\bGTP_SCANCHAIN\w*\b', re.I)


def adapt_runner(code):
    start = '        write_lines(stage / "probe.tcl",'
    stop = '        write_lines(stage / "build.tcl",'
    if code.count(start) != 1 or code.count(stop) != 1:
        raise ValueError('ILA stage boundaries changed')
    first, last = code.index(start), code.index(stop)
    if last <= first:
        raise ValueError('Unexpected ILA stage order')
    code = code[:first] + code[last:]
    code = replace_once(code,
        '"ila": {"data_channels":42,"trigger_channels":33,"depth":1024,"clock":"cpu_clk"}',
        '"instrumentation_profile": "none", "ila": ' + repr(NO_ILA))
    code = replace_once(code,
        '["add_fic " + tcl_path(stage / "cpu-remapped.fic"),"set_arch',
        '["set_arch')
    code = replace_once(code,
        '("source.adf","netlist.v","cpu-remapped.fic","build.tcl","mapping-audit.json","fetch-alias-proof.json")',
        '("source.adf","netlist.v","build.tcl")')
    code = code.replace('full historical ILA', 'ILA omitted')
    code = replace_once(code, '        for name, original in templates.items():',
        '        for name in ("audit_fetch_ila.py", "audit_ila_mapping.py", "ila_pipeline_minimal_config.py", "template.fic", "redirect_fetch_alias.py"):\n'
        '            templates.pop(name, None)\n'
        '        templates["physical_instrumentation.py"] = ROOT / "scripts/physical_instrumentation.py"\n'
        '        helper.snapshot(ROOT / "ILA_PUBLICATION_DECISION.md", source / "ILA_PUBLICATION_DECISION.md")\n'
        '        for name, original in templates.items():')
    anchor = '        helper.write_json(stage / "multicorner-audit.json",timing_audit)'
    code = replace_once(code, anchor, anchor + '\n'
        '        instrumentation = load_module(source / "tools/physical_instrumentation.py", "frozen_instrumentation")\n'
        '        record["instrumentation_audit"] = instrumentation.audit_no_ila(run, record)\n'
        '        helper.write_json(stage / "instrumentation-audit.json", record["instrumentation_audit"])')
    compile(code, 'ila-free-runner', 'exec')
    return code


def audit_no_ila(run, manifest=None):
    from run_embench import sha
    from review_r30_synthesis_guard import reported_setup_budget
    if manifest is None:
        manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest.get('instrumentation_profile') != 'none' or manifest.get('ila') != NO_ILA:
        raise ValueError('Explicit ILA-free metadata required')
    stage = run / 'implementation'
    commands = (stage / 'build.tcl').read_text(encoding='utf-8-sig')
    if re.search(r'(?im)^\s*(?:add_fic|ins_\w+)\b|\.fic\b', commands):
        raise ValueError('ILA insertion command found')
    for pattern in ('*.fic', 'probe*', 'verify*', 'mapping-audit.json', 'fetch-alias-proof.json'):
        if list(stage.glob(pattern)):
            raise ValueError('ILA insertion artifacts present: ' + pattern)
    inventory = json.loads((stage / 'input-hashes.json').read_text())
    if set(inventory) != {'source.adf', 'netlist.v', 'build.tcl'}:
        raise ValueError('Unexpected ILA-free implementation inputs')
    for name, digest in inventory.items():
        if sha(stage / name) != digest:
            raise ValueError('Implementation input changed: ' + name)
    artifacts = [stage / 'netlist.v', stage / 'run.log', stage / 'report_timing/pds_soc_top.rtr']
    for path in artifacts:
        if DEBUG_NET.search(path.read_text(encoding='utf-8-sig')):
            raise ValueError('Pango debug hierarchy or scan-chain primitive found: ' + str(path))
    budgets = reported_setup_budget(artifacts[-1], 0.150)
    return dict(profile='none', ila_enabled=False, insertion_commands_absent=True,
                insertion_artifacts_absent=True, known_pango_debug_hierarchy_absent=True,
                reported_cpu_setup_uncertainty_ns=budgets,
                evidence_hashes={p.relative_to(run).as_posix(): sha(p) for p in artifacts},
                scope='Frozen synthesized inputs, insertion commands, native implementation log and timing report; no claim of arbitrary hidden-circuit detection.')
