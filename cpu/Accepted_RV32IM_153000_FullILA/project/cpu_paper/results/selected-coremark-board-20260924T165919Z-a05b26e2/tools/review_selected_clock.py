"""Recheck selected-clock implementation identities, native timing and routes.

Preserve the existing v27/153 MHz qualification gates. Generate narrowly adapted,
archived validators for v28; never treat a timing-derived estimate as closure.
"""
import argparse
import csv
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import re
from uuid import uuid4
import run_embench as h
import embench_board_evidence as board
import redirect_physical_binding as binding
from audit_physical_timing import audit
from create_redirect_optimization import replace_once
from run_selected_clock import CLOCKS, MODE, VARIANTS
import selected_clock_profiles as profiles


def validators(clock, protocol='v28'):
    if protocol not in ('v27', 'v28') or (protocol == 'v27' and clock != 153000000):
        raise ValueError('Unsupported physical protocol/clock')
    common=inspect.getsource(board.physical_artifacts_binding)
    common=replace_once(common,'153000000)',str(clock)+')')
    ns=dict(vars(board)); exec(compile(common,'selected-common-validator','exec'),ns)
    selected=inspect.getsource(binding.physical_binding)
    if protocol == 'v28':
        selected=replace_once(selected,"pm.get('protocol')!='v27'","pm.get('protocol')!='v28'")
    selected=replace_once(selected,'configured_clock_hz=153000000','configured_clock_hz='+str(clock))
    selected=replace_once(selected,"if fm.get('protocol')!='v26' or fm.get('status')!='built':",
        "if fm.get('protocol')!='v26' or fm.get('status')!='built' or fm.get('configured_clock_hz')!="+str(clock)+':')
    bn=dict(vars(binding)); bn['physical_artifacts_binding']=ns['physical_artifacts_binding']
    bn['PROFILES']=profiles.PROFILES; bn['command']=profiles.command
    exec(compile(selected,'selected-identity-validator','exec'),bn)
    return bn['physical_binding'], common, selected


def paths(report):
    rows=[]
    for block in re.split(r'(?m)(?=^Startpoint\s*:)',report.read_text())[1:]:
        kind=re.search(r'^Path Type\s*:\s*(.*)$',block,re.M)
        group=re.search(r'^Path Group\s*:\s*(.*)$',block,re.M)
        if not kind or kind[1].strip()!='max (slow corner)' or not group or 'CLKOUT0_Inferred' not in group[1]:
            continue
        # PDS also labels asynchronous recovery paths "max (slow corner)".
        # They remain covered by the full timing audit, but are not setup paths.
        if re.search(r'^ Recovery time\s+',block,re.M): continue
        start=re.search(r'^Startpoint\s*:\s*(.*)$',block,re.M)
        end=re.search(r'^Endpoint\s*:\s*(.*)$',block,re.M)
        slack=re.search(r'^ Slack \((?:MET|VIOLATED)\)\s+(-?\d+\.\d+)',block,re.M)
        delay=re.search(r'Logic: ([\d.]+)ns\(([\d.]+)%\), Route: ([\d.]+)ns\(([\d.]+)%\)',block)
        skew=re.search(r'^Clock Skew\s*:\s*(-?[\d.]+)',block,re.M)
        uncertainty=re.search(r'^ clock uncertainty\s+(-?[\d.]+)',block,re.M)
        setup=re.search(r'^ Setup time\s+(-?[\d.]+)',block,re.M)
        data_start=re.search(r'^.*\btco\s+.*$',block,re.M)
        if not all((start,end,slack,delay,skew,uncertainty,setup,data_start)): raise ValueError('Unrecognized setup path')
        data=block[data_start.start():block.index(' Data arrival time',data_start.start())]
        nets=[dict(fanout=int(m[1]),delay_ns=float(m[2]),name=m[3].strip())
              for m in re.finditer(r'^\s+net \(fanout=(\d+)\)\s+([\d.]+)\s+[\d.]+\s+(.*)$',data,re.M)]
        if not nets: raise ValueError('No data nets')
        rows.append(dict(rank=len(rows)+1,startpoint=start[1].strip(),endpoint=end[1].strip(),
            setup_slack_ns=float(slack[1]),logic_ns=float(delay[1]),route_ns=float(delay[3]),
            route_percent=float(delay[4]),maximum_data_fanout=max(n['fanout'] for n in nets),
            clock_skew_ns=float(skew[1]),clock_uncertainty_ns=-float(uncertainty[1]),setup_requirement_ns=-float(setup[1]),
            largest_route_nets=sorted(nets,key=lambda n:n['delay_ns'],reverse=True)[:5]))
    if not rows: raise ValueError('No reported slow CPU setup paths')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('physical',type=Path); p.add_argument('--firmware',type=Path,required=True)
    p.add_argument('--variants',type=Path,default=VARIANTS)
    args=p.parse_args(); physical=args.physical.resolve(); firmware=args.firmware.resolve()
    variants=args.variants.resolve()
    pm=board.read(physical/'manifest.json'); clock=pm['configured_clock_hz']
    if (not variants.is_relative_to((h.ROOT/'variants').resolve()) or
            pm.get('variant_manifest_sha256')!=h.sha(variants/'manifest.json')):
        raise ValueError('Requested variant identity differs from native evidence')
    if clock not in CLOCKS or pm.get('protocol')!='v28' or pm.get('variant')!=MODE:
        raise ValueError('Not the selected v28 implementation')
    if pm['status'] not in ('timing_failed','internal_timing_passed'):
        raise ValueError('Implementation not terminal')
    # Reparse the raw report even for failures. The qualified-image validator below
    # deliberately rejects failed images and is only invoked after a fresh pass.
    for name,digest in pm['output_hashes'].items():
        if h.sha(physical/name)!=digest: raise ValueError('Changed native output')
    # The parser emits diagnostic tuples; manifests serialize them as lists.
    timing=json.loads(json.dumps(audit(physical)))
    if timing!=pm['timing_audit']: raise ValueError('Timing audit differs')
    from run_physical_ila import load_module, text
    report=load_module(physical/'inputs/tools/pds_report.py','selected_report').parse_ila_reports(
        text(physical/'implementation/report_timing/pds_soc_top.rtr'),text(physical/'implementation/run.log'),clock)
    if report!=pm['report']: raise ValueError('Reparsed native report differs')
    if abs(report['cpu_period_ns']-1e9/clock)>0.002:
        raise ValueError('Reported PLL period differs from selected clock')
    passed=timing['internal_multicorner_timing_passed'] and report['constraints_met']
    if pm.get('instrumentation_profile') == 'none':
        from physical_instrumentation import audit_no_ila
        if audit_no_ila(physical, pm) != pm.get('instrumentation_audit'):
            raise ValueError('ILA-free audit differs')
    if passed!=(pm['status']=='internal_timing_passed'): raise ValueError('Timing status contradiction')
    check,common,selected=validators(clock)
    if passed: check(physical,variants,MODE,firmware)
    route=paths(physical/'implementation/report_timing/pds_soc_top.rtr')
    run=h.ROOT/'results'/('selected-clock-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    for name,code in (('common-validator.py',common),('identity-validator.py',selected)):
        (run/name).write_text(code,encoding='utf-8')
    for path in (Path(__file__),Path(board.__file__),Path(binding.__file__),Path(profiles.__file__),h.ROOT/'protocol_v28_selected_clock.md'):
        h.snapshot(path,run/'tools'/path.name)
    row=dict(physical=str(physical),configured_clock_hz=clock,measured_clock_hz=None,
        status='native_timing_and_identity_verified' if passed else 'timing_failed',
        qualified_bitstream=passed,hardware_validated=False,seed=pm['placement_seed'],
        profile=pm['implementation_profile'],instrumentation_profile=pm.get('instrumentation_profile','full'),
        setup_wns_ns=timing['cpu_setup_wns_ns'],
        hold_wns_ns=timing['cpu_hold_wns_ns'],lut=report['resources']['post_route_luts'],
        ff=report['resources']['post_route_ffs'],drm=report['resources']['DRM'],apm=report['resources']['APM'],
        critical_route_percent=route[0]['route_percent'],critical_route_ns=route[0]['route_ns'],
        critical_logic_ns=route[0]['logic_ns'],bitstream_sha256=pm['bitstream_sha256'])
    row.update(critical_clock_skew_ns=route[0]['clock_skew_ns'],
        critical_setup_requirement_ns=route[0]['setup_requirement_ns'],
        critical_clock_uncertainty_ns=route[0]['clock_uncertainty_ns'])
    h.write_json(run/'result.json',row); h.write_json(run/'paths.json',route)
    with (run/'results.csv').open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(row)); writer.writeheader(); writer.writerow(row)
    h.write_json(run/'manifest.json',dict(protocol='v28',status='reviewed',result=row,
        variants=str(variants),variant_manifest_sha256=h.sha(variants/'manifest.json'),
        physical_manifest_sha256=h.sha(physical/'manifest.json'),firmware_manifest_sha256=h.sha(firmware/'manifest.json'),
        note='Reported paths are limited report coverage, not all paths. Failed images are not qualified.',
        tool_hashes={f.relative_to(run).as_posix():h.sha(f) for f in run.rglob('*') if f.is_file()}))
    print(json.dumps(row),flush=True); print(run,flush=True)


if __name__=='__main__': main()
