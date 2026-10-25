"""Read-only v27 image binding; does not authorize or perform programming."""
import argparse
from pathlib import Path
import run_embench as h
from embench_board_evidence import read,physical_artifacts_binding
from redirect_implementation_profiles import PROFILES, command


def physical_binding(physical,variants,variant,firmware):
    physical=Path(physical).resolve(); variants=Path(variants).resolve(); firmware=Path(firmware).resolve()
    for directory,category in ((physical,'results'),(firmware,'results'),(variants,'variants')):
        if not directory.is_relative_to((h.ROOT/category).resolve()): raise ValueError('Evidence outside project '+category)
    if not variant or Path(variant).name!=variant or variant in ('.','..'):
        raise ValueError('Invalid variant name')
    pm=read(physical/'manifest.json'); vm=read(variants/'manifest.json'); fm=read(firmware/'manifest.json')
    if (physical/'qualification-correction.json').exists(): raise ValueError('Superseded or rejected qualification')
    if (vm.get('protocol')!='v27' or pm.get('protocol')!='v27' or pm.get('firmware_protocol')!='v26'
            or variant not in vm.get('variants',{})):
        raise ValueError('Explicit v27 variant identity required')
    if pm.get('status')!='internal_timing_passed': raise ValueError('Candidate did not pass native timing')
    if pm.get('variant')!=variant or Path(pm['source_reference']).resolve()!=variants/variant:
        raise ValueError('Physical variant identity differs')
    digest=h.sha(variants/'manifest.json')
    if pm.get('variant_manifest_sha256')!=digest or h.sha(physical/'inputs/variant-manifest.json')!=digest:
        raise ValueError('Physical variant manifest differs')
    expected=dict(device='PG2L200H-6FBB676',implementation_tool='Windows PDS 2022.2-SP6.4 ADS',
                  configured_clock_hz=153000000,workload='uart-loader',uart_profile='RemoteLab',uart_baud=115200)
    for key,value in expected.items():
        if pm.get(key)!=value: raise ValueError('Physical configuration differs: '+key)
    if pm.get('hardware_parameters')!=h.PARAMS: raise ValueError('Protocol hardware parameters differ')
    if pm.get('placement_seed') not in (1,2,3): raise ValueError('Unsupported placement seed')
    profile=pm.get('implementation_profile','default')
    if profile not in PROFILES or pm.get('implementation_options',[])!=PROFILES[profile]:
        raise ValueError('Unsupported implementation profile/options')
    commands=[line.strip() for line in (physical/'implementation/build.tcl').read_text(encoding='utf-8-sig').splitlines()
              if line.strip().startswith('pnr ')]
    if commands!=[command(profile,pm['placement_seed'])]:
        raise ValueError('Native implementation command differs from declared profile')
    for relative,expected_hash in vm['variants'][variant]['hashes'].items():
        rel=Path(relative)
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('Unsafe source manifest path')
        if h.sha(variants/variant/rel)!=expected_hash: raise ValueError('Variant source changed: '+relative)
        if rel.parts[0] in ('rtl','fpga','constraints'):
            if h.sha(physical/'inputs'/rel)!=expected_hash: raise ValueError('Physical RTL/constraint differs: '+relative)
    if fm.get('protocol')!='v26' or fm.get('status')!='built': raise ValueError('Frozen v26 loader firmware required')
    firmware_digest=h.sha(firmware/'manifest.json')
    if pm.get('firmware_manifest_sha256')!=firmware_digest or h.sha(physical/'inputs/firmware-manifest.json')!=firmware_digest:
        raise ValueError('Physical firmware manifest differs')
    if h.sha(firmware/'source-hashes.json')!=fm['source_manifest_sha256']:
        raise ValueError('Firmware source inventory changed')
    for relative,expected_hash in read(firmware/'source-hashes.json').items():
        rel=Path(relative)
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('Unsafe firmware source path')
        if h.sha(firmware/'inputs'/rel)!=expected_hash: raise ValueError('Firmware source changed')
    loaders=[r for r in fm['results'] if r.get('workload')=='uart-loader']
    if len(loaders)!=1 or pm.get('firmware')!=loaders[0]: raise ValueError('Loader build identity differs')
    if h.sha(firmware/'workloads/uart-loader/firmware.hex')!=loaders[0]['firmware_sha256']:
        raise ValueError('Loader image changed')
    # Reparse native timing and resource reports, hashes, bitstream and ILA map.
    # This remains mandatory even if a receipt's status field claims a pass.
    return physical_artifacts_binding(physical,pm)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('physical',type=Path); p.add_argument('variants',type=Path)
    p.add_argument('variant'); p.add_argument('firmware',type=Path)
    args=p.parse_args()
    pm,timing=physical_binding(args.physical,args.variants,args.variant,args.firmware)
    print('Physical identity and internal timing verified; architectural, benchmark, seed-selection and board gates remain separate.')
    print('bitstream_sha256='+pm['bitstream_sha256'])


if __name__=='__main__': main()
