"""Evaluate the installed DDR IP's timing rules in a separate generated copy."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literal(value: str) -> str:
    if any(c in value for c in '{}\\\n\r'):
        raise ValueError('Unsupported Tcl literal')
    return '{' + value + '}'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rate-mbps', type=float, required=True)
    args = parser.parse_args()
    if not 600 <= args.rate_mbps <= 1066.666:
        parser.error('DDR3 requested rate must be within 600..1066.666 Mbps')
    pds = Path(os.environ.get('PDS_ROOT', 'D:/PDS_2022.2-SP6.4'))
    model = pds / 'ip/system_ip/ips2l_hmic_s/ips2l_hmic_eval/ips2l_hmic_s'
    source = ROOT / 'ipcore/ddr3_test'
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    out = ROOT / 'build/pacerv_shared_system/ddr_clock' / (stamp + '-' + str(args.rate_mbps))
    out.mkdir(parents=True, exist_ok=False)
    copied = out / 'ddr3_test'
    shutil.copytree(source, copied)
    original = source / 'ddr3_test.idf'
    tree = ET.parse(original)
    params = {p.findtext('name'): p.findtext('value', '')
              for p in tree.findall('./param_list/param')}
    original_hashes = {p.relative_to(source).as_posix(): sha(p)
                       for p in source.rglob('*') if p.is_file()}
    # Evaluate the vendor's clock and memory-timing procedures directly.
    # Pin assignment stays frozen; package-pin GUI queries are not rerun.
    # Every parameter read must exist and any dialog request becomes an error.
    lines = ['set params [dict create]']
    lines += ['dict set params ' + literal(k) + ' ' + literal(v) for k, v in params.items()]
    lines += [
        'rename ::ui::getModelPath ::ui::getModelPath_native',
        'proc ::ui::getModelPath {} {return ' + literal(model.as_posix()) + '}',
        'rename ::ui::getValue ::ui::getValue_native',
        'proc ::ui::getValue {args} {global params; set i [lsearch -exact $args -name]; '
        'if {$i < 0} {set i [lsearch -exact $args -n]}; '
        'if {$i < 0} {error {missing parameter name}}; '
        'return [dict get $params [lindex $args [expr {$i+1}]]]}',
        'rename ::ui::setValue ::ui::setValue_native',
        'proc ::ui::setValue {args} {global params; set i [lsearch -exact $args -name]; '
        'if {$i < 0} {set i [lsearch -exact $args -n]}; '
        'set j [lsearch -exact $args -value]; '
        'if {$i < 0 || $j < 0} {error {missing parameter name/value}}; '
        'dict set params [lindex $args [expr {$i+1}]] [lindex $args [expr {$j+1}]]}',
        'foreach {cmd value} {getDevice PG2L100H getFamily Logos2 getPackage FBG676 getSpeedGrade -6} '
        '{rename ::ui::$cmd ::ui::${cmd}_native; proc ::ui::$cmd {} [list return $value]}',
        'foreach cmd {setText show hide enable disable setItems} {proc ::ui::$cmd {args} {}}',
        'proc ::ui::popupMessage {args} {error [format {DDR validation: %s} $args]}',
        'source ' + literal((model / 'ui.tcl').as_posix()),
        'set dq_bank_group_recfg 0',
        'ui::setValue -name DESIRED_DDR3_RATE -value ' + str(args.rate_mbps),
        'upd_data_rate', 'upd_write_read_latency',
        'set mem_clk [expr {double([ui::getValue -name ACTUAL_RATE])/2.0}]',
        'set mem_clk_period_ps [expr {1000000.0/$mem_clk}]',
        'set mem_clk_period_ns [expr {1000.0/$mem_clk}]',
        'set dfi_clk_period [expr {4.0*$mem_clk_period_ps}]',
        'ui::setValue -name DFI_CLK_PERIOD -value [expr {int($dfi_clk_period)}]',
        'check_mr_ddr3_wr $mem_clk_period_ns', 'check_mr_ddr3_cl',
        'check_pll_bandwidth',
        'check_timing_para $dfi_clk_period $mem_clk_period_ps',
        'check_device_100h', 'check_chip_dq_width',
        'set f [open ' + literal((out / 'evaluated.tsv').as_posix()) + ' w]',
        'dict for {key value} $params {puts $f [format {%s\t%s} $key $value]}',
        'close $f', 'puts {DDR_RULES_PASS}', 'exit',
    ]
    script = out / 'evaluate.tcl'
    script.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    command = [str(pds / 'bin/ip_generate.exe'), '-disable-syn', '-f', str(script)]
    run = subprocess.run(command, cwd=out, capture_output=True, timeout=60,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    output = (run.stdout + run.stderr).decode('utf-8', errors='replace')
    (out / 'evaluate.log').write_text(output, encoding='utf-8')
    if run.returncode or 'DDR_RULES_PASS' not in output:
        errors = [line for line in output.splitlines() if line.startswith('E:')]
        raise RuntimeError(f'DDR rules failed ({run.returncode}): {errors}; {out}')
    evaluated = dict(line.split('\t', 1) for line in
                     (out / 'evaluated.tsv').read_text().splitlines())
    changes = {k: {'before': params.get(k), 'after': v}
               for k, v in evaluated.items() if params.get(k) != v}
    # Replace only values, keeping every other byte of the baseline IDF.
    text = original.read_bytes().decode('utf-8')
    for key, change in changes.items():
        pattern = r'(<name>' + re.escape(key) + r'</name>\s*<value>)[^<]*(</value>)'
        text, count = re.subn(pattern, lambda m: m[1] + change['after'] + m[2], text)
        if count != 1:
            raise RuntimeError('IDF parameter replacement count: ' + key)
    target = copied / 'ddr3_test.idf'
    target.write_bytes(text.encode('utf-8'))
    command = [str(pds / 'bin/ip_generate.exe'), '-disable-syn', '-i', str(target)]
    run = subprocess.run(command, cwd=out, capture_output=True, timeout=60,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    output = (run.stdout + run.stderr).decode('utf-8', errors='replace')
    (out / 'generate.log').write_text(output, encoding='utf-8')
    if run.returncode or re.search(r'^E:', output, re.M):
        raise RuntimeError('DDR generation failed: ' + str(out))
    if any(sha(source / p) != value for p, value in original_hashes.items()):
        raise RuntimeError('Live DDR IP changed')
    changed_files = [name for name, value in original_hashes.items()
                     if sha(copied / name) != value]
    rtl_changed = [name for name in changed_files if name.endswith(('.v', '.vp'))]
    original_rate = float(params['ACTUAL_RATE'])
    if float(evaluated['ACTUAL_RATE']) == original_rate and rtl_changed:
        raise RuntimeError('Original-rate regeneration changed RTL: ' + str(rtl_changed))
    report = {'requested_rate_mbps': args.rate_mbps,
              'actual_rate_mbps': float(evaluated['ACTUAL_RATE']),
              'system_clock_hz': float(evaluated['ACTUAL_RATE']) * 1e6 / 8,
              'parameter_changes': changes, 'original_ip_hashes': original_hashes,
              'changed_original_files': changed_files,
              'validation_scope': 'Vendor clock/CL/CWL/memory timing rules and generation; '
                                  'original package-pin assignment retained unchanged; '
                                  'complete implementation and hardware not qualified by this helper',
              'vendor_rules_sha256': sha(model / 'ui.tcl'),
              'pll_rules_sha256': sha(model / 'createDivideParam.tcl'),
              'commands_passed': True, 'live_ip_unchanged': True,
              'generated_directory': str(copied)}
    (out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    assert json.loads((out / 'RESULT.json').read_text()) == report
    print('DDR_CLOCK_PREPARED ' + str(out))
    print(f'DDR_RULES_PASS rate_mbps={report["actual_rate_mbps"]} '
          f'system_clock_hz={report["system_clock_hz"]} changed_parameters={len(changes)} live_unchanged=1')


if __name__ == '__main__':
    main()
