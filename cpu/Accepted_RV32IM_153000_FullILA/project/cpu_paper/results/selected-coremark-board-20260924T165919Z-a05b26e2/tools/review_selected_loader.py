"""Bind rebuilt clock-specific loader smoke tests to raw execution evidence."""
import argparse
from datetime import datetime, timezone
import inspect
from pathlib import Path
from uuid import uuid4
import run_embench as h
import embench_board_evidence as board
import redirect_loader_binding as loader
from create_redirect_optimization import replace_once
from run_selected_clock import CLOCKS, MODE, VARIANTS


def validators(clock, protocol='v28'):
    if clock not in CLOCKS: raise ValueError('Unsupported selected clock')
    if protocol not in ('v27', 'v28') or (protocol == 'v27' and clock != 153000000):
        raise ValueError('Unsupported loader protocol/clock')
    frame=inspect.getsource(board.parse_frame)
    if frame.count('153000000')!=3: raise ValueError('Frame clock anchors changed')
    frame=frame.replace('153000000',str(clock))
    fn=dict(vars(board)); exec(compile(frame,'selected-frame-validator','exec'),fn)
    bind=inspect.getsource(loader.bind)
    if protocol == 'v28':
        bind=replace_once(bind,"rm.get('protocol') == 'v27'","rm.get('protocol') == 'v28'")
    bind=replace_once(bind,"rm.get('configured_clock_hz') == 153000000","rm.get('configured_clock_hz') == "+str(clock))
    if protocol == 'v28':
        bind=replace_once(bind,"return dict(protocol='v27'","return dict(protocol='v28'")
    anchor="    variant_hash, firmware_hash = h.sha(variants / 'manifest.json'), h.sha(firmware / 'manifest.json')"
    bind=replace_once(bind,anchor,"    require(fm.get('configured_clock_hz') == "+str(clock)+", 'Firmware clock differs')\n"+anchor)
    bn=dict(vars(loader)); bn['parse_frame']=fn['parse_frame']
    exec(compile(bind,'selected-loader-validator','exec'),bn)
    return bn['bind'],fn['parse_frame'],bind,frame


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('smoke',type=Path); p.add_argument('--firmware',type=Path,required=True)
    p.add_argument('--variants',type=Path,default=VARIANTS)
    args=p.parse_args(); fm=board.read(args.firmware/'manifest.json')
    variants=args.variants.resolve()
    if not variants.is_relative_to((h.ROOT/'variants').resolve()):
        raise ValueError('Variant directory is outside the project')
    check,_,bind,frame=validators(fm['configured_clock_hz'])
    result=check([args.smoke],variants,MODE,args.firmware)
    run=h.ROOT/'results'/('selected-loader-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    (run/'bind.py').write_text(bind,encoding='utf-8'); (run/'frame.py').write_text(frame,encoding='utf-8')
    for original in (Path(__file__),Path(board.__file__),Path(loader.__file__)):
        h.snapshot(original,run/'tools'/original.name)
    h.write_json(run/'manifest.json',dict(protocol='v28',status='passed',configured_clock_hz=fm['configured_clock_hz'],
        variants=str(variants),variant_manifest_sha256=h.sha(variants/'manifest.json'),
        result=result,source_hashes={p.relative_to(run).as_posix():h.sha(p) for p in run.rglob('*') if p.is_file()}))
    print(run,flush=True)


if __name__=='__main__': main()
