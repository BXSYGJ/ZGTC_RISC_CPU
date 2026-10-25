"""Independently reparse the 153 MHz area candidate's source and timing evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
import run_embench as h
from embench_board_evidence import read
from review_selected_clock import validators, paths


def main():
    p=argparse.ArgumentParser()
    p.add_argument('physical',type=Path)
    p.add_argument('--variants',type=Path,required=True)
    p.add_argument('--firmware',type=Path,required=True)
    args=p.parse_args()
    check,common,selected=validators(153000000,'v27')
    pm,timing=check(args.physical,args.variants,'accepted_valid_ram',args.firmware)
    if pm['placement_seed']!=3:
        raise ValueError('Seed differs from declared experiment')
    rows=paths(args.physical/'implementation/report_timing/pds_soc_top.rtr')
    if any(abs(row['clock_uncertainty_ns']-0.150)>1e-9 for row in rows):
        raise ValueError('Original setup uncertainty not retained')
    if pm['report']['resources']['post_route_luts']>=9502:
        raise ValueError('Resource reduction not achieved')
    run=h.ROOT/'results'/('accepted-area-physical-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir()
    for name in ('review_accepted_area_physical.py','review_selected_clock.py','redirect_physical_binding.py',
                 'embench_board_evidence.py','selected_clock_profiles.py','audit_physical_timing.py','physical_instrumentation.py'):
        h.snapshot(h.ROOT/'scripts'/name,run/'tools'/name)
    (run/'common-validator.py').write_text(common,encoding='utf-8')
    (run/'selected-validator.py').write_text(selected,encoding='utf-8')
    record=dict(status='passed',physical=str(args.physical.resolve()),
        physical_manifest_sha256=h.sha(args.physical/'manifest.json'),
        variant_manifest_sha256=h.sha(args.variants/'manifest.json'),
        firmware_manifest_sha256=h.sha(args.firmware/'manifest.json'),
        instrumentation_profile=pm.get('instrumentation_profile','full'),
        report=pm['report'],timing=json.loads(json.dumps(timing)),paths=rows,
        source_hashes={p.relative_to(run).as_posix():h.sha(p) for p in run.rglob('*') if p.is_file()})
    h.write_json(run/'review.json',record)
    print(run,flush=True)


if __name__=='__main__': main()
